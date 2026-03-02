"""
Bot tests for prisoners_dilemma.

Flow (with USE_BATCH_START):
  InformedConsent -> MainInstructions -> lobby -> InstructionsNoDelegation -> DecisionNoDelegation
  -> wait for everyone in group to finish -> Results -> lobby -> InstructionsDelegation -> AgentProgramming
  -> wait for everyone in group to finish -> Results -> ...

- lobby: wait until at least 10 participants are present, then form a new group. Bots do not yield it;
  the runner adds bots when it sees they are on Lobby (by URL or AssertionError) and, when 10 are pending,
  GETs Lobby for all 10 twice so everyone gets the redirect (no generator advance).
- wait for everyone in group to finish: implemented as BatchWaitForGroup; waits until all in the group
  have submitted so Results can be shown. Runner GETs that page for all 10, waits, GETs again, then advances.
"""
import os
import random
import re
from urllib.parse import urlparse

from otree.api import *
from otree.lookup import get_page_lookup
from otree.bots.bot import Submission
from otree.models import Participant

from .models import Constants
from .pages import (
    BATCH_WAIT_MIN_SECONDS,
    AgentProgramming,
    BatchWaitForGroup,
    BotDetection,
    ComprehensionTest,
    DecisionNoDelegation,
    DelegationDecision,
    Debriefing,
    ExitQuestionnaire,
    FailedTest,
    GuessDelegation,
    InformedConsent,
    InstructionsDelegation,
    InstructionsGuessingGame,
    InstructionsNoDelegation,
    InstructionsOptional,
    Lobby,
    MainInstructions,
    Results,
    ResultsGuess,
    Thankyou,
    WaitForGroup,
    WaitForGroupWithTimeout,
)

os.environ.setdefault('OTREE_SKIP_CSRF', '1')

# Must match Constants.DELEGATION_FIRST so bot and app stay in sync.
TEST_DELEGATION_FIRST = Constants.DELEGATION_FIRST


def _part(rnd):
    return Constants.get_part(rnd)


def _is_mandatory_delegation_round(rnd):
    if TEST_DELEGATION_FIRST:
        return _part(rnd) == 1
    return _part(rnd) == 2


def _is_no_delegation_round(rnd):
    if _part(rnd) == 3:
        return False
    return not _is_mandatory_delegation_round(rnd)


# ---------------------------------------------------------------------------
# Runner patch: lobby (gather 10, form group) + wait for everyone in group (BatchWaitForGroup)
# ---------------------------------------------------------------------------

class _LobbySubmission:
    """Sentinel so runner treats "participant on Lobby" without the bot yielding Lobby."""
    page_class = Lobby


def _is_lobby_submission(s):
    return (
        Constants.USE_BATCH_START
        and getattr(getattr(s, 'page_class', None), '__name__', None) == 'Lobby'
    )


def _is_batch_wait_submission(s):
    """Wait for everyone in group to finish (before Results)."""
    return (
        Constants.USE_BATCH_START
        and getattr(getattr(s, 'page_class', None), '__name__', None) == 'BatchWaitForGroup'
    )


def _bot_id_in_session(bot):
    """ParticipantBot has participant_code, not participant; load id_in_session from DB."""
    return Participant.objects_get(code=bot.participant_code).id_in_session


def _bots_in_same_matching_group(runner_self, bot):
    """Return list of (pid, other_bot) for bots in the same matching group as bot (for BatchWaitForGroup).
    Uses id_in_session so batch 1-10 -> group 0, 11-20 -> 1, etc., matching app's sorted(lobby)[:10] release order."""
    group_index = (_bot_id_in_session(bot) - 1) // Constants.matching_group_size
    out = []
    for pid, other_bot in list(runner_self.bots.items()):
        if (_bot_id_in_session(other_bot) - 1) // Constants.matching_group_size == group_index:
            out.append((pid, other_bot))
    return out


def _do_lobby_flush(batch, path_parts, lobby_round_int):
    """Flush one batch from lobby: GET Lobby for all 10 twice so each gets redirect. Do not advance generators."""
    lobby_path_suffix = ['Lobby', str(lobby_round_int)]
    for _bid, b, _sub in batch:
        url_b = '/' + '/'.join([path_parts[0], b.participant_code] + path_parts[2:3] + lobby_path_suffix)
        b.response = b.client.get(url_b, allow_redirects=True)
    for _bid, b, _sub in batch:
        url_b = '/' + '/'.join([path_parts[0], b.participant_code] + path_parts[2:3] + lobby_path_suffix)
        b.response = b.client.get(url_b, allow_redirects=True)
        if getattr(b.response, 'status_code', 0) in (200, 302, 303):
            b.url = getattr(b.response, 'url', url_b) or url_b
            b.path = urlparse(b.url).path


def _patch_runner():
    from urllib.parse import urlparse
    from otree.bots.runner import SessionBotRunner

    _original_play = SessionBotRunner.play

    def _play(self):
        self.open_start_urls()
        loops_without_progress = 0
        lobby_pending = []
        lobby_flush_count = 0
        batches_per_part = max(1, len(self.bots) // 10)

        while True:
            if not self.bots:
                return
            if loops_without_progress > 10:
                raise AssertionError('Bots got stuck')

            playable_ids = list(self.bots.keys())
            if len(lobby_pending) == 9:
                pending_ids = {pid for pid, _, _ in lobby_pending}
                playable_ids = sorted(playable_ids, key=lambda pid: (0 if pid not in pending_ids else 1, pid))

            progress_made = False
            pending_ids = {p for p, _, _ in lobby_pending}

            def flush_lobby_if_10():
                nonlocal progress_made, loops_without_progress, lobby_flush_count
                if len(lobby_pending) < 10:
                    return
                # App releases first 10 by sorted id_in_session; match that order so matching_group_id aligns
                batch = sorted(lobby_pending, key=lambda x: _bot_id_in_session(x[1]))[:10]
                batch_pids = {x[0] for x in batch}
                lobby_pending[:] = [x for x in lobby_pending if x[0] not in batch_pids]
                first_bot = batch[0][1]
                parsed = urlparse(first_bot.url)
                path_parts = [p for p in parsed.path.split('/') if p]
                lobby_round_int = (1, 11, 21)[min(lobby_flush_count // batches_per_part, 2)]
                lobby_flush_count += 1
                _do_lobby_flush(batch, path_parts, lobby_round_int)
                progress_made = True
                loops_without_progress = 0

            for pid in playable_ids:
                if pid not in self.bots:
                    continue
                bot = self.bots[pid]
                # lobby: bot on Lobby page → add without advancing generator; flush when 10
                if Constants.USE_BATCH_START and 'Lobby' in (getattr(bot, 'url', None) or ''):
                    if pid not in pending_ids:
                        lobby_pending.append((pid, bot, _LobbySubmission()))
                        progress_made = True
                    flush_lobby_if_10()
                    continue
                if bot.on_wait_page():
                    continue
                # 9 in lobby: add 10th without get_next_submit so generator stays in sync
                if len(lobby_pending) == 9 and pid not in pending_ids:
                    lobby_pending.append((pid, bot, _LobbySubmission()))
                    progress_made = True
                    flush_lobby_if_10()
                    continue

                try:
                    submission = bot.get_next_submit()
                except AssertionError as e:
                    msg = str(e)
                    # Handle both classic oTree wording ("participant is actually here")
                    # and newer wording ("Discrepancy between bot code and app code").
                    if (
                        "participant is actually here" not in msg
                        and "Discrepancy between bot code and app code" not in msg
                    ):
                        raise
                    pages = re.findall(r"'page':\s*'(\w+)'", msg)
                    actual_page = pages[1] if len(pages) > 1 else (pages[0] if pages else '')  # participant's current page
                    if actual_page == 'Lobby' and Constants.USE_BATCH_START:
                        lobby_pending.append((pid, bot, _LobbySubmission()))
                        progress_made = True
                        flush_lobby_if_10()
                        continue
                    # Bot yielded Results (we skipped DecisionNoDelegation for rnd 10/20/30) but participant still on DecisionNoDelegation -> submit it first
                    if actual_page == 'DecisionNoDelegation' and 'Results' in msg and Constants.USE_BATCH_START:
                        m_rnd = re.search(r"'round_number':\s*(\d+)", msg)
                        rnd_val = int(m_rnd.group(1)) if m_rnd else 0
                        if rnd_val in (10, 20, 30):
                            bot.submit(Submission(DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}))
                            progress_made = True
                            continue
                    if actual_page == 'BatchWaitForGroup' and Constants.USE_BATCH_START:
                        # wait for everyone in group to finish: GET only same-group bots, wait, GET again
                        import time as time_module
                        group_bots = _bots_in_same_matching_group(self, bot)
                        part = Participant.objects_get(code=bot.participant_code)
                        idx = part.vars.get('_index_in_pages')
                        try:
                            idx = int(idx) if idx is not None else None
                        except (TypeError, ValueError):
                            idx = None
                        if idx is None and (bot.url or bot.path):
                            try:
                                path = (urlparse(bot.url or bot.path or '').path or '').strip('/')
                                idx = int(path.rsplit('/', maxsplit=1)[-1])
                            except (ValueError, TypeError, IndexError):
                                pass
                        if idx is not None and group_bots:
                            parsed = urlparse(bot.url or '')
                            path_parts = [p for p in (parsed.path or '').split('/') if p]
                            app_name = path_parts[2] if len(path_parts) > 2 else 'prisoners_dilemma'
                            for _oid, other_bot in group_bots:
                                other_path = '/' + '/'.join([path_parts[0], other_bot.participant_code, app_name, 'BatchWaitForGroup', str(idx)])
                                other_url = parsed._replace(path=other_path).geturl()
                                other_bot.response = other_bot.client.get(other_url, allow_redirects=True)
                            time_module.sleep(max(0, BATCH_WAIT_MIN_SECONDS) + 0.5)
                            for _oid, other_bot in group_bots:
                                other_path = '/' + '/'.join([path_parts[0], other_bot.participant_code, app_name, 'BatchWaitForGroup', str(idx)])
                                other_url = parsed._replace(path=other_path).geturl()
                                other_bot.response = other_bot.client.get(other_url, allow_redirects=True)
                        progress_made = True
                        continue
                    # General catch-up: participant is ahead (e.g. round 21 vs bot round 11); submit actual page until in sync
                    rounds = re.findall(r"'round_number':\s*(\d+)", msg)
                    actual_round = int(rounds[1]) if len(rounds) > 1 else (int(rounds[0]) if rounds else 0)
                    lookup = {'page': actual_page, 'round_number': actual_round}
                    class _LookupParticipant:
                        pass
                    _lp = _LookupParticipant()
                    for _ in range(100):
                        _lp.participant = Participant.objects_get(code=bot.participant_code)
                        payload = _yield_for_lookup(_lp, lookup)
                        if not payload:
                            raise
                        page_class, form = payload
                        if page_class is Thankyou:
                            bot.submit(Submission(Thankyou, {}, check_html=False))
                        elif form is not None:
                            bot.submit(Submission(page_class, form))
                        else:
                            bot.submit(Submission(page_class, {}))
                        try:
                            submission = bot.get_next_submit()
                            break
                        except StopIteration:
                            self.bots.pop(pid, None)
                            progress_made = True
                            submission = None
                            break
                        except AssertionError as e2:
                            msg = str(e2)
                            if "participant is actually here" not in msg:
                                raise
                            pages = re.findall(r"'page':\s*'(\w+)'", msg)
                            actual_page = pages[1] if len(pages) > 1 else (pages[0] if pages else '')
                            rounds = re.findall(r"'round_number':\s*(\d+)", msg)
                            actual_round = int(rounds[1]) if len(rounds) > 1 else (int(rounds[0]) if rounds else 0)
                            lookup = {'page': actual_page, 'round_number': actual_round}
                    else:
                        raise AssertionError('Catch-up failed after 100 attempts')
                    if submission is None:
                        progress_made = True
                        continue
                except StopIteration:
                    self.bots.pop(pid, None)
                    progress_made = True
                    continue

                if _is_lobby_submission(submission):
                    if pid not in [p for p, _, _ in lobby_pending]:
                        lobby_pending.append((pid, bot, submission))
                    submission = None
                if len(lobby_pending) >= 10:
                    flush_lobby_if_10()
                if submission is None:
                    progress_made = True
                    continue

                if _is_batch_wait_submission(submission):
                    # wait for everyone in group to finish: GET only same-group bots, wait, GET again, advance their generators
                    import time as time_module
                    group_bots = _bots_in_same_matching_group(self, bot)
                    parsed = urlparse(bot.url)
                    path_parts = [p for p in parsed.path.split('/') if p]
                    if len(path_parts) >= 5:
                        app_name = path_parts[2]
                        page_name = path_parts[3]
                        page_index = path_parts[4]
                        for _oid, other_bot in group_bots:
                            other_path = '/' + '/'.join([path_parts[0], other_bot.participant_code, app_name, page_name, page_index])
                            other_url = parsed._replace(path=other_path).geturl()
                            other_bot.response = other_bot.client.get(other_url, allow_redirects=True)
                    wait_sec = max(0, BATCH_WAIT_MIN_SECONDS) + 0.5
                    time_module.sleep(wait_sec)
                    for _oid, other_bot in group_bots:
                        other_path = '/' + '/'.join([path_parts[0], other_bot.participant_code, app_name, page_name, page_index])
                        other_url = parsed._replace(path=other_path).geturl()
                        other_bot.response = other_bot.client.get(other_url, allow_redirects=True)
                        if getattr(other_bot.response, 'status_code', 0) in (302, 303):
                            other_bot.url = getattr(other_bot.response, 'url', other_url) or other_url
                            other_bot.path = urlparse(other_bot.url).path
                    for _oid, other_bot in group_bots:
                        try:
                            other_bot.get_next_submit()
                        except StopIteration:
                            self.bots.pop(_oid, None)
                    progress_made = True
                    loops_without_progress = 0
                    continue
                else:
                    bot.submit(submission)
                progress_made = True
                loops_without_progress = 0

            # Stale lobby: 2–9 bots waiting, all in lobby_pending → wait then flush
            if (
                Constants.USE_BATCH_START
                and 2 <= len(lobby_pending) < 10
                and set(bid for bid, _, _ in lobby_pending) == set(self.bots.keys())
            ):
                import time
                time.sleep(20)
                batch = list(lobby_pending)
                lobby_pending.clear()
                first_bot = batch[0][1]
                parsed = urlparse(first_bot.url)
                path_parts = [p for p in parsed.path.split('/') if p]
                lobby_round_int = (1, 11, 21)[min(lobby_flush_count // batches_per_part, 2)]
                lobby_flush_count += 1
                _do_lobby_flush(batch, path_parts, lobby_round_int)
                progress_made = True
                loops_without_progress = 0

            if not progress_made:
                loops_without_progress += 1

    SessionBotRunner.play = _play


_patch_runner()


# ---------------------------------------------------------------------------
# Catch-up: yield the page the participant is actually on (by lookup)
# ---------------------------------------------------------------------------

def _yield_for_lookup(bot_self, lookup):
    """Return (page_class, form_data) or None. Do not yield Lobby (wait page)."""
    page_name = getattr(lookup, 'page', None) or (lookup.get('page') if hasattr(lookup, 'get') else None)
    rnd = getattr(lookup, 'round_number', None) or (lookup.get('round_number') if hasattr(lookup, 'get') else None)
    if page_name is None or rnd is None:
        return None
    if page_name == 'Lobby':
        return None
    if page_name == 'InformedConsent':
        return (InformedConsent, {'prolific_id': f'TESTBOT_{bot_self.participant.id_in_session:03d}'})
    if page_name == 'BotDetection':
        return (BotDetection, None)
    if page_name == 'MainInstructions':
        return (MainInstructions, None)
    if page_name == 'ComprehensionTest':
        return (ComprehensionTest, COMPREHENSION_ANSWERS)
    if page_name == 'FailedTest':
        return (FailedTest, None)
    if page_name == 'DecisionNoDelegation':
        return (DecisionNoDelegation, {'choice': random.choice(['A', 'B'])})
    if page_name == 'WaitForGroup':
        return (WaitForGroup, None)
    if page_name == 'WaitForGroupWithTimeout':
        return (WaitForGroupWithTimeout, None)
    if page_name == 'BatchWaitForGroup':
        return None  # wait for everyone in group to finish; runner handles
    if page_name == 'Results':
        return (Results, None)
    if page_name == 'InstructionsOptional':
        return (InstructionsOptional, None)
    if page_name == 'InstructionsNoDelegation':
        return (InstructionsNoDelegation, None)
    if page_name == 'InstructionsDelegation':
        return (InstructionsDelegation, None)
    if page_name == 'DelegationDecision':
        if 'bot_delegate_choice_part3' not in bot_self.participant.vars:
            bot_self.participant.vars['bot_delegate_choice_part3'] = random.choice([True, False])
        return (DelegationDecision, {'delegate_decision_optional': bot_self.participant.vars['bot_delegate_choice_part3']})
    if page_name == 'AgentProgramming':
        if rnd == 21 and not bot_self.participant.vars.get('agent_programming_part3'):
            bot_self.participant.vars['agent_programming_part3'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
        return (AgentProgramming, None)
    if page_name == 'InstructionsGuessingGame':
        return (InstructionsGuessingGame, None)
    if page_name == 'GuessDelegation':
        return (GuessDelegation, {f'guess_round_{i}': random.choice(['yes', 'no']) for i in range(1, 11)})
    if page_name == 'ResultsGuess':
        return (ResultsGuess, None)
    if page_name == 'Debriefing':
        return (Debriefing, None)
    if page_name == 'ExitQuestionnaire':
        return (ExitQuestionnaire, {
            'gender': random.choice(['male', 'female', 'nonbinary', 'nosay']),
            'age': random.randint(18, 80),
            'occupation': 'Bot tester',
            'ai_use': random.choice(['never', 'monthly', 'weekly', 'daily', 'constant']),
            'task_difficulty': random.choice(['very_diff', 'diff', 'neutral', 'easy', 'very_easy']),
            'part_3_feedback': random.choice(['more_fun', 'faster', 'greedy', 'utilitarian', 'random']),
            'part_3_feedback_other': '',
            'part_4_feedback': random.choice(['expected_del_A', 'expected_no_del_A', 'same_action', 'opposite_action', 'random']),
            'part_4_feedback_other': '',
            'feedback': 'Automated bot test.',
        })
    if page_name == 'Thankyou':
        return (Thankyou, None)
    return None


# ---------------------------------------------------------------------------
# Bot: play_round
# ---------------------------------------------------------------------------

EXIT_QUESTIONNAIRE_DATA = {
    'gender': random.choice(['male', 'female', 'nonbinary', 'nosay']),
    'age': random.randint(18, 80),
    'occupation': 'Bot tester',
    'ai_use': random.choice(['never', 'monthly', 'weekly', 'daily', 'constant']),
    'task_difficulty': random.choice(['very_diff', 'diff', 'neutral', 'easy', 'very_easy']),
    'part_3_feedback': random.choice(['more_fun', 'faster', 'greedy', 'utilitarian', 'random']),
    'part_3_feedback_other': '',
    'part_4_feedback': random.choice(['expected_del_A', 'expected_no_del_A', 'same_action', 'opposite_action', 'random']),
    'part_4_feedback_other': '',
    'feedback': 'Automated bot test.',
}

COMPREHENSION_ANSWERS = {
    'q1': 'c', 'q2': 'b', 'q3': 'c', 'q4': 'c', 'q5': 'a',
    'q6': 'c', 'q7': 'a', 'q8': 'b', 'q9': 'b', 'q10': 'b',
}


class PlayerBot(Bot):
    def play_round(self):
        rnd = self.round_number
        session_code = getattr(getattr(self, 'participant_bot', None), 'session_code', None) or self.session.code
        idx = getattr(self.participant, '_index_in_pages', None)
        if idx is None and getattr(self, 'participant_bot', None):
            path = getattr(self.participant_bot, 'path', None) or ''
            try:
                idx = int(path.rsplit('/', maxsplit=1)[-1])
            except (ValueError, TypeError, IndexError):
                pass
        if idx is not None and session_code:
            try:
                lookup = get_page_lookup(session_code, idx)
                if lookup:
                    actual_rnd = getattr(lookup, 'round_number', None) or (lookup.get('round_number') if hasattr(lookup, 'get') else None)
                    if actual_rnd is not None:
                        payload = _yield_for_lookup(self, lookup)
                        if payload:
                            page_class, form = payload
                            if page_class is Thankyou:
                                yield Submission(Thankyou, {}, check_html=False)
                            elif form is not None:
                                yield page_class, form
                            else:
                                yield page_class
                            return
            except (KeyError, TypeError, AttributeError):
                pass

        # ----- Round 1: consent, bot check, instructions, comprehension -----
        if rnd == 1:
            yield InformedConsent, {'prolific_id': f'TESTBOT_{self.participant.id_in_session:03d}'}
            # BotDetection only shown when prolific_id == "1234567890GenerativeAI4U"; skip for normal test bots
            if self.player.field_maybe_none('prolific_id') == '1234567890GenerativeAI4U':
                yield BotDetection
            yield MainInstructions
            yield ComprehensionTest, COMPREHENSION_ANSWERS
            if self.player.is_excluded:
                yield FailedTest
                return
            # lobby is not yielded; runner adds bot when on Lobby and flushes when 10.
            if TEST_DELEGATION_FIRST:
                yield InstructionsDelegation
                self.participant.vars['agent_programming_part1'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
                yield AgentProgramming
            else:
                yield InstructionsNoDelegation

        # ----- Part 1 / Part 2 no-delegation decision rounds -----
        # Always yield DecisionNoDelegation on the app's decision rounds; BatchWaitForGroup is a wait page
        # in between decision and Results, so having both pages in the generator keeps browser bots in sync.
        if _is_no_delegation_round(rnd):
            yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}

        # ----- Round 10: results (after BatchWaitForGroup wait page) -----
        if rnd == 10:
            yield Results

        # # ----- Round 11: Lobby (automatic), Part 2 instructions -----
        if rnd == 11 and TEST_DELEGATION_FIRST:
            yield InstructionsNoDelegation
        elif rnd == 11 and not TEST_DELEGATION_FIRST:
            yield InstructionsDelegation
            self.participant.vars['agent_programming_part2'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
            yield AgentProgramming

        # # ----- Round 20: results -----
        if rnd == 20:
            yield Results

        # # # ----- Round 21: Lobby (automatic), Part 3 instructions, delegation choice -----
        if rnd == 21:
            if 'bot_delegate_choice_part3' not in self.participant.vars:
                self.participant.vars['bot_delegate_choice_part3'] = random.choice([True, False])
            yield InstructionsOptional
            yield DelegationDecision, {'delegate_decision_optional': self.participant.vars['bot_delegate_choice_part3']}
            if self.participant.vars['bot_delegate_choice_part3']:
                if not self.participant.vars.get('agent_programming_part3'):
                    self.participant.vars['agent_programming_part3'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
                yield AgentProgramming
            else:
                yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}

        # # # ----- Part 3 rounds 22–30: decision or skip -----
        if _part(rnd) == 3 and rnd >= 22:
            delegates = self.player.field_maybe_none('delegate_decision_optional')
            # If the participant did NOT delegate, they see DecisionNoDelegation on every round 22–30,
            # including round 30; then BatchWaitForGroup (wait page) and finally Results.
            if not delegates:
                yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}
            if rnd == 30:
                yield Results
                yield InstructionsGuessingGame

        # # # ----- Part 4 (round 30): guessing, debrief, exit, thankyou -----
        if rnd == Constants.num_rounds:
            yield GuessDelegation, {f'guess_round_{i}': random.choice(['yes', 'no']) for i in range(1, 11)}
            yield ResultsGuess
            yield Debriefing
            yield ExitQuestionnaire, EXIT_QUESTIONNAIRE_DATA
            yield Submission(Thankyou, {}, check_html=False)
