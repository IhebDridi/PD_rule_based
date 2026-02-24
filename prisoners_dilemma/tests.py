from otree.api import *
from .models import Constants
from .pages import *
import random


class PlayerBot(Bot):

    def play_round(self):
        rnd = self.round_number
        part = Constants.get_part(rnd)
        end_of_part = (rnd % Constants.rounds_per_part == 0)

        # =================================================
        # ROUND 1 — Consent + main instructions
        # =================================================
        if rnd == 1:
            yield InformedConsent, {
                'prolific_id': f'TESTBOT_{self.participant.id_in_session:03d}'
            }
            yield MainInstructions

            yield ComprehensionTest, {
                'q1': 'c',
                'q2': 'b',
                'q3': 'c',
                'q4': 'c',
                'q5': 'a',
                'q6': 'c',
                'q7': 'a',
                'q8': 'b',
                'q9': 'b',
                'q10': 'b',
            }

        # =================================================
        # PART 1 — Mandatory delegation
        # =================================================
        if part == 1 and (rnd - 1) % Constants.rounds_per_part == 0:
            yield InstructionsDelegation

            yield Submission(
                AgentProgramming,
                {
                    f'agent_decision_mandatory_delegation_round_{i}':
                        random.choice(['A', 'B'])
                    for i in range(1, 11)
                },
                check_html=False
            )

        # ❌ NO Results for Part 1
        # (your app logic skips them)

        # =================================================
        # PART 2 — No delegation
        # =================================================
        if part == 2 and (rnd - 1) % Constants.rounds_per_part == 0:
            yield InstructionsNoDelegation

        if part == 2:
            yield DecisionNoDelegation, {
                'choice': random.choice(['A', 'B'])
            }

        # ✅ Results at end of Part 2
        if part == 2 and end_of_part:
            yield Results

        # =================================================
        # PART 3 — Optional delegation
        # =================================================
        if part == 3 and (rnd - 1) % Constants.rounds_per_part == 0:
            yield InstructionsOptional

            delegate = random.choice([True, False])
            yield DelegationDecision, {
                'delegate_decision_optional': delegate
            }

            if delegate:
                yield Submission(
                    AgentProgramming,
                    {
                        f'decision_optional_delegation_round_{i}':
                            random.choice(['A', 'B'])
                        for i in range(1, 11)
                    },
                    check_html=False
                )

        # ✅ Results at end of Part 3
        if part == 3 and end_of_part and rnd < Constants.num_rounds:
            yield Results

        # =================================================
        # GUESSING GAME + END
        # =================================================
        if rnd == Constants.num_rounds:
            yield InstructionsGuessingGame

            yield Submission(
                GuessDelegation,
                {
                    f'guess_round_{i}': random.choice(['yes', 'no'])
                    for i in range(1, 11)
                },
                check_html=False
            )

            yield ResultsGuess
            yield Debriefing

            part3_reason = random.choice(
                ['more_fun', 'faster', 'greedy', 'utilitarian', 'random']
            )
            part4_reason = random.choice(
                ['expected_del_A', 'expected_no_del_A',
                 'same_action', 'opposite_action', 'random']
            )

            yield ExitQuestionnaire, {
                'gender': random.choice(['male', 'female', 'nonbinary', 'nosay']),
                'age': random.randint(18, 80),
                'occupation': 'Bot tester',
                'ai_use': random.choice(
                    ['never', 'monthly', 'weekly', 'daily', 'constant']
                ),
                'task_difficulty': random.choice(
                    ['very_diff', 'diff', 'neutral', 'easy', 'very_easy']
                ),
                'part_3_feedback': part3_reason,
                'part_3_feedback_other': '',
                'part_4_feedback': part4_reason,
                'part_4_feedback_other': '',
                'feedback': 'Automated browser‑bot test.',
            }