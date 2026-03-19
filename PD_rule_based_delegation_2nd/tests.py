"""
Bot tests for prisoners_dilemma. Run: otree test prisoners_dilemma --num_participants 6
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
    MainInstructions,
    Results,
    ResultsGuess,
    Thankyou,
)

# Correct answers for comprehension test (bots pass so they are not excluded)
COMPREHENSION_ANSWERS = {
    'q1': 'c', 'q2': 'b',
    'q6': 'c', 'q7': 'a', 'q8': 'd', 'q9': 'b', 'q10': 'b',
}

os.environ.setdefault('OTREE_SKIP_CSRF', '1')

DELEGATION_FIRST = Constants.DELEGATION_FIRST


def _part(rnd):
    return Constants.get_part(rnd)


def _is_mandatory_delegation(rnd):
    return _part(rnd) == (1 if DELEGATION_FIRST else 2)


def _is_no_delegation(rnd):
    return _part(rnd) != 3 and not _is_mandatory_delegation(rnd)


# UNUSED (commented out): Lobby runner patch
#
# The Lobby page is currently disabled; grouping happens only at BatchWaitForGroup.
# The special runner patch for Lobby is not needed.


def _patch_runner():
    from otree.bots.runner import SessionBotRunner

    def _play(self):
        self.open_start_urls()
        loops_without_progress = 0
        # Lobby is disabled; no lobby flush / release logic needed.

        while True:
            if not self.bots:
                return
            if loops_without_progress > 10:
                raise AssertionError('Bots got stuck')

            playable_ids = list(self.bots.keys())
            pending_ids = {p for p, _, _ in lobby_pending}
            if len(lobby_pending) == Constants.MIN_PLAYERS_TO_START - 1:
                playable_ids = sorted(playable_ids, key=lambda pid: (0 if pid not in pending_ids else 1, pid))

            progress_made = False

            def flush_lobby_if_ready():
                nonlocal progress_made, loops_without_progress, lobby_flush_count
                if len(lobby_pending) < Constants.MIN_PLAYERS_TO_START:
                    return
                batch = sorted(lobby_pending, key=lambda x: _bot_id_in_session(x[1]))[:Constants.MIN_PLAYERS_TO_START]
                batch_pids = {x[0] for x in batch}
                lobby_pending[:] = [x for x in lobby_pending if x[0] not in batch_pids]
                parsed = urlparse(batch[0][1].url)
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

                if 'Lobby' in (getattr(bot, 'url', None) or ''):
                    if pid not in pending_ids:
                        lobby_pending.append((pid, bot, _LobbySubmission()))
                        progress_made = True
                    flush_lobby_if_ready()
                    continue
                if bot.on_wait_page():
                    continue
                if len(lobby_pending) == Constants.MIN_PLAYERS_TO_START - 1 and pid not in pending_ids:
                    lobby_pending.append((pid, bot, _LobbySubmission()))
                    progress_made = True
                    flush_lobby_if_ready()
                    continue

                try:
                    submission = bot.get_next_submit()
                except AssertionError as e:
                    msg = str(e)
                    if "participant is actually here" not in msg and "Discrepancy between bot code and app code" not in msg:
                        raise
                    pages = re.findall(r"'page':\s*'(\w+)'", msg)
                    actual_page = pages[1] if len(pages) > 1 else (pages[0] if pages else '')
                    if actual_page == 'Lobby':
                        lobby_pending.append((pid, bot, _LobbySubmission()))
                        progress_made = True
                        flush_lobby_if_ready()
                        continue
                    if actual_page == 'DecisionNoDelegation' and 'Results' in msg:
                        m = re.search(r"'round_number':\s*(\d+)", msg)
                        if m and int(m.group(1)) in (10, 20, 30):
                            bot.submit(Submission(DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}))
                            progress_made = True
                            continue
                    if actual_page == 'BatchWaitForGroup':
                        import time as time_module
                        group_bots = _bots_in_same_matching_group(self, bot)
                        part = Participant.objects_get(code=bot.participant_code)
                        idx = part.vars.get('_index_in_pages')
                        if idx is None and (bot.url or bot.path):
                            try:
                                idx = int(urlparse(bot.url or bot.path or '').path.strip('/').rsplit('/', 1)[-1])
                            except (ValueError, TypeError, IndexError):
                                pass
                        if idx is not None and group_bots:
                            parsed = urlparse(bot.url or '')
                            path_parts = [p for p in (parsed.path or '').split('/') if p]
                            app = path_parts[2] if len(path_parts) > 2 else 'prisoners_dilemma'
                            for _oid, other_bot in group_bots:
                                path = '/' + '/'.join([path_parts[0], other_bot.participant_code, app, 'BatchWaitForGroup', str(idx)])
                                other_bot.response = other_bot.client.get(parsed._replace(path=path).geturl(), allow_redirects=True)
                            time_module.sleep(max(0, BATCH_WAIT_MIN_SECONDS) + 0.5)
                            for _oid, other_bot in group_bots:
                                path = '/' + '/'.join([path_parts[0], other_bot.participant_code, app, 'BatchWaitForGroup', str(idx)])
                                other_bot.response = other_bot.client.get(parsed._replace(path=path).geturl(), allow_redirects=True)
                        progress_made = True
                        continue
                    rounds = re.findall(r"'round_number':\s*(\d+)", msg)
                    actual_round = int(rounds[1]) if len(rounds) > 1 else (int(rounds[0]) if rounds else 0)
                    payload = _yield_for_lookup(bot, {'page': actual_page, 'round_number': actual_round})
                    if payload:
                        page_class, form = payload
                        if page_class is Thankyou:
                            bot.submit(Submission(Thankyou, {}, check_html=False))
                        else:
                            bot.submit(Submission(page_class, form or {}))
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
                if len(lobby_pending) >= Constants.MIN_PLAYERS_TO_START:
                    flush_lobby_if_ready()
                if submission is None:
                    progress_made = True
                    continue

                bot.submit(submission)
                progress_made = True
                loops_without_progress = 0

            if (len(lobby_pending) >= Constants.MIN_PLAYERS_TO_START and
                    set(bid for bid, _, _ in lobby_pending) == set(self.bots.keys())):
                import time
                time.sleep(2)
                batch = list(lobby_pending)
                lobby_pending.clear()
                parsed = urlparse(batch[0][1].url)
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


def _exit_form():
    return {
        'gender': random.choice(['male', 'female', 'nonbinary', 'nosay']),
        'age': random.randint(18, 80),
        'occupation': 'Bot',
        'ai_use': random.choice(['never', 'monthly', 'weekly', 'daily', 'constant']),
        'task_difficulty': random.choice(['very_diff', 'diff', 'neutral', 'easy', 'very_easy']),
        'part_3_feedback': random.choice(['more_fun', 'faster', 'greedy', 'utilitarian', 'random']),
        'part_3_feedback_other': '',
        'part_4_feedback': random.choice(['expected_del_A', 'expected_no_del_A', 'same_action', 'opposite_action', 'random']),
        'part_4_feedback_other': '',
        'feedback': '',
    }


def _yield_for_lookup(bot_self, lookup):
    """Catch-up: return (page_class, form_data) for the page participant is on."""
    page_name = lookup.get('page') if isinstance(lookup, dict) else getattr(lookup, 'page', None)
    rnd = lookup.get('round_number') if isinstance(lookup, dict) else getattr(lookup, 'round_number', None)
    if not page_name or rnd is None:
        return None
    if page_name == 'Lobby' or page_name == 'BatchWaitForGroup':
        return None
    pid = getattr(bot_self.participant, 'id_in_session', 0)
    if page_name == 'InformedConsent':
        return (InformedConsent, {'prolific_id': f'TESTBOT_{pid:03d}'})
    if page_name == 'MainInstructions':
        return (MainInstructions, None)
    if page_name == 'ComprehensionTest':
        return (ComprehensionTest, COMPREHENSION_ANSWERS)
    if page_name == 'FailedTest':
        return (FailedTest, None)
    if page_name == 'InstructionsNoDelegation':
        return (InstructionsNoDelegation, None)
    if page_name == 'InstructionsDelegation':
        return (InstructionsDelegation, None)
    if page_name == 'InstructionsOptional':
        return (InstructionsOptional, None)
    if page_name == 'InstructionsGuessingGame':
        return (InstructionsGuessingGame, None)
    if page_name == 'DecisionNoDelegation':
        return (DecisionNoDelegation, {'choice': random.choice(['A', 'B'])})
    if page_name == 'Results':
        return (Results, None)
    if page_name == 'DelegationDecision':
        return (DelegationDecision, {'delegate_decision_optional': random.choice([True, False])})
    if page_name == 'AgentProgramming':
        if rnd == 21:
            bot_self.participant.vars['agent_programming_part3'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
        return (AgentProgramming, None)
    if page_name == 'GuessDelegation':
        return (GuessDelegation, {f'guess_round_{i}': random.choice(['yes', 'no']) for i in range(1, 11)})
    if page_name == 'ResultsGuess':
        return (ResultsGuess, None)
    if page_name == 'Debriefing':
        return (Debriefing, None)
    if page_name == 'ExitQuestionnaire':
        return (ExitQuestionnaire, _exit_form())
    if page_name == 'Thankyou':
        return (Thankyou, None)
    return None


class PlayerBot(Bot):
    def play_round(self):
        rnd = self.round_number

        # Sync with actual page when behind (e.g. after lobby redirect)
        session_code = getattr(getattr(self, 'participant_bot', None), 'session_code', None) or getattr(self.session, 'code', None)
        idx = getattr(self.participant, '_index_in_pages', None)
        if idx is None and getattr(self, 'participant_bot', None):
            try:
                idx = int((getattr(self.participant_bot, 'path', None) or '').rsplit('/', 1)[-1])
            except (ValueError, TypeError, IndexError):
                pass
        if idx is not None and session_code:
            try:
                lookup = get_page_lookup(session_code, idx)
                if lookup:
                    actual_rnd = lookup.get('round_number') if isinstance(lookup, dict) else getattr(lookup, 'round_number', None)
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

        if rnd == 1:
            yield InformedConsent, {'prolific_id': f'TESTBOT_{getattr(self.participant, "id_in_session", 0):03d}'}
            yield MainInstructions
            yield ComprehensionTest, COMPREHENSION_ANSWERS
            if DELEGATION_FIRST:
                yield InstructionsDelegation
            else:
                yield InstructionsNoDelegation
            if DELEGATION_FIRST:
                self.participant.vars['agent_programming_part1'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
                yield AgentProgramming
            else:
                yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}

        if _is_no_delegation(rnd) and rnd != 1:
            yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}

        if rnd == 10:
            yield Results

        if rnd == 11:
            if DELEGATION_FIRST:
                yield InstructionsNoDelegation
            else:
                yield InstructionsDelegation
            if DELEGATION_FIRST:
                yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}
            else:
                self.participant.vars['agent_programming_part2'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
                yield AgentProgramming

        if rnd == 20:
            yield Results

        if rnd == 21:
            # Match page_sequence: InstructionsOptional then DelegationDecision. Runner catch-up submits the actual page when bot and participant disagree.
            yield InstructionsOptional
            delegate = random.choice([True, False])
            yield DelegationDecision, {'delegate_decision_optional': delegate}
            if delegate:
                self.participant.vars['agent_programming_part3'] = {i: random.choice(['A', 'B']) for i in range(1, 11)}
                yield AgentProgramming
            else:
                yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}

        if _part(rnd) == 3 and rnd >= 22:
            if not self.player.field_maybe_none('delegate_decision_optional'):
                yield DecisionNoDelegation, {'choice': random.choice(['A', 'B'])}
            if rnd == 30:
                yield Results

        if rnd == Constants.num_rounds:
            yield InstructionsGuessingGame
            yield GuessDelegation, {f'guess_round_{i}': random.choice(['yes', 'no']) for i in range(1, 11)}
            yield ResultsGuess
            yield Debriefing
            yield ExitQuestionnaire, _exit_form()
            yield Submission(Thankyou, {}, check_html=False)
