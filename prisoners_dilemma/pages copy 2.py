from otree.api import *
from .models import Constants
import json
import pandas as pd
import settings


# -----------------------------
#  General Introduction & Setup
# -----------------------------

class InformedConsent(Page):
    form_model = 'player'
    form_fields = ['prolific_id']
    def is_displayed(self):
        return self.round_number == 1  # Show only once at the beginning
    def error_message_prolific_id(self, value):
        print('error check informed consesnte')
        pid = value.get('prolific_id', '')
        if len(value.strip()) != 24:
            return "Please make sure that your Prolific ID is correct. You will not be able to proceed in the experiment without providing your Prolific ID."


""" class Introduction(Page):
    def is_displayed(self):
        return self.round_number == 1  # Show only once at the beginning """


class ComprehensionTest(Page):
    form_model = 'player'
    form_fields = ['q1', 'q2', 'q3', 'q4', 'q5',
                   'q6', 'q7', 'q8', 'q9', 'q10']

    def is_displayed(self):
        return self.round_number == 1 and not self.player.is_excluded

    def vars_for_template(self):
        return {
            "comp_error_message": self.participant.vars.get(
                "comp_error_message"
            ),
        }

    def error_message(self, values):
        correct_answers = {
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

        incorrect = [
            q for q, correct in correct_answers.items()
            if values.get(q) != correct
        ]

        if not incorrect:
            # ✅ all correct → proceed
            self.participant.vars.pop("comp_error_message", None)
            return

        # ❌ incorrect answers
        self.player.comprehension_attempts += 1
        attempts_left = 3 - self.player.comprehension_attempts

        if attempts_left > 0:
            msg = (
                f"You have failed questions: {', '.join(incorrect)}. "
                f"You have {attempts_left} attempt(s) remaining."
            )
            self.participant.vars["comp_error_message"] = msg
            return msg

        # 🚫 no attempts left → exclude
        self.player.is_excluded = True
        return (
            "You have failed the comprehension test too many times "
            "and cannot continue with the experiment."
        )


class FailedTest(Page):
    def is_displayed(self):
        return self.player.is_excluded

# -------------------------
#  Per-Part Instructions
# -------------------------

""" class Instructions(Page):
    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)
        return not self.player.is_excluded and (self.round_number - 1) % Constants.rounds_per_part == 0

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        return {
            'current_part': current_part,
            'incorrect_answers': self.player.incorrect_answers,

        } """


# -------------------------
#  Agent Programming
# -------------------------

class AgentProgramming(Page):
    form_model = 'player'

    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)

        # Part 1: mandatory delegation (once)
        if current_part == 1:
            return (self.round_number - 1) % Constants.rounds_per_part == 0

        # Part 3: optional delegation, only if delegated
        if current_part == 3:
            return (
                self.player.field_maybe_none("delegate_decision_optional") is True
                and (self.round_number - 1) % Constants.rounds_per_part == 0
            )

        return False

    def get_form_fields(self):
        current_part = Constants.get_part(self.round_number)

        # ✅ Part 1: mandatory delegation
        if current_part == 1:
            return [
                f"agent_decision_mandatory_delegation_round_{i}"
                for i in range(1, 11)
            ]

        # ✅ Part 3: optional delegation
        if current_part == 3:
            return [
                f"decision_optional_delegation_round_{i}"
                for i in range(1, 11)
            ]

        return []

    def vars_for_template(self):
        return {
            'current_part': Constants.get_part(self.round_number),
            'delegate_decision': self.player.field_maybe_none(
                'delegate_decision_optional'
            ),
        }

    def before_next_page(self):
        current_part = Constants.get_part(self.round_number)

        # ============================
        # PART 1 — mandatory delegation
        # ============================
        if current_part == 1:
            anchor = self.player  # ✅ round 1

            for i in range(1, 11):
                decision = anchor.field_maybe_none(
                    f"agent_decision_mandatory_delegation_round_{i}"
                )

                if decision is None:
                    raise RuntimeError(
                        f"Agent decision missing in programming: round {i}"
                    )

            # ✅ NOTHING ELSE HERE
            # ✅ Do NOT set choice here
            # ✅ Do NOT write to other rounds
"""         if current_part == 1:
            start_round = 1

            for i in range(1, 11):
                future = self.player.in_round(start_round + i - 1)

                decision = self.player.field_maybe_none(
                    f"decision_optional_delegation_round_{i}"
                )

                if decision is not None:
                    future.choice = decision

                # store agent plan
                setattr(
                    future,
                    f"agent_decision_mandatory_delegation_round_{i}",
                    decision
                )

                # apply to actual play
                future.choice = decision """

        # ============================
        # PART 3 — optional delegation
        # ============================


        
# -------------------------
#  waiting page
# -------------------------
class WaitForGroup(WaitPage):

    def is_displayed(self):
        return self.round_number % Constants.rounds_per_part == 0

    def after_all_players_arrive(self):
        # ✅ DEFINE current_part
        current_part = Constants.get_part(self.round_number)

        # =========================
        # PART 1 — mandatory delegation
        # =========================
        if current_part == 1:
            for p in self.group.get_players():
                anchor = p.in_round(1)  # agent plan lives here

                for i in range(1, 11):
                    pr = p.in_round(i)

                    decision = anchor.field_maybe_none(
                        f"agent_decision_mandatory_delegation_round_{i}"
                    )

                    if decision is None:
                        raise RuntimeError(
                            f"Missing agent decision for player {p.id_in_group}, round {i}"
                        )

                    pr.choice = decision

        # =========================
        # PAYOFFS (TEMP: unconditional)
        # =========================
        for r in range(
            (current_part - 1) * Constants.rounds_per_part + 1,
            current_part * Constants.rounds_per_part + 1
        ):
            self.group.in_round(r).set_payoffs()



# -------------------------
#  Decision Making
# -------------------------

""" class Decision(Page):
    form_model = 'player'
    form_fields = ['choice']
    #timeout_seconds = 20


    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)
        return current_part == 2 or (current_part == 3 and not self.player.delegate_decision_optional)

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1
        allocation = None
        if current_part == 1:
            allocation = self.player.get_agent_decision_mandatory(display_round)
        elif current_part == 3 and self.player.delegate_decision_optional:
            allocation = self.player.get_agent_decision_optional(display_round)
        #add logic to add allocation for part 1:

        return {
            'round_number': display_round,
            'current_part': current_part,
            'decision_mode': (
                "agent" if (current_part == 1 or (current_part == 3 and self.player.delegate_decision_optional)) else "manual"
            ),
            'player_allocation': allocation,
            'alert_message': self.participant.vars.get('alert_message', ""),
        }

    def before_next_page(self):
        import json
        import random

        #decisions = json.loads(self.player.random_decisions)
        #print(f"[DEBUG] Existing random_decisions: {decisions}")

        # Get current part and display round
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1

        if current_part == 2 or (current_part == 3 and not self.player.delegate_decision_optional)  :  # Part 1 logic or Part 3 with manual with manual decisions and timer
  
                self.participant.vars['alert_message'] = None
                self.player.random_decisions = False
                

            # Update decisions for the current round



        elif current_part == 1:  # Mandatory delegation
            self.player.allocation = self.player.get_agent_decision_mandatory(display_round)
            self.participant.vars['alert_message'] = ""
            self.player.random_decisions = True
            self.player.delegate_decision_optional = False 

        elif current_part == 3 and self.player.delegate_decision_optional:  # Optional delegation
            self.player.allocation = self.player.get_agent_decision_optional(display_round)
            self.participant.vars['alert_message'] = ""
            self.player.random_decisions = False
            self.player.delegate_decision_optional = True
        




        # elif current_part == 3 and not self.player.delegate_decision_optional:  # Manual decision

        #     #self.player.allocation = self.player.get_agent_decision_optional(display_round)
        #     self.player.random_decisions = False
        #     self.player.delegate_decision_optional = False
        #     self.player.allocation = self.player.get_agent_decision_optional(display_round)



        #print(f"round:{self.round_number}  self.player.allocation: {self.player.allocation}")
 """


# -------------------------
#  Delegation Decision
# -------------------------

class DelegationDecision(Page):
    form_model = 'player'
    form_fields = ['delegate_decision_optional']

    def is_displayed(self):
        # show ONCE at start of Part 3 (round 21)
        return (
            Constants.get_part(self.round_number) == 3
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )

    def before_next_page(self):
        # copy decision into ALL Part 3 rounds (21–30)
        start_round = 2 * Constants.rounds_per_part + 1  # 21
        end_round = 3 * Constants.rounds_per_part        # 30

        for r in range(start_round, end_round + 1):
            self.player.in_round(r).delegate_decision_optional = (
                self.player.delegate_decision_optional
            )
            print(
            "DELEGATION DECISION:",
            self.player.id_in_group,
            self.player.delegate_decision_optional
        )

        start_round = 21
        end_round = 30

        for r in range(start_round, end_round + 1):
            p = self.player.in_round(r)
            p.delegate_decision_optional = self.player.delegate_decision_optional
            print(" → wrote to round", r)
        # 🚨 FORCE PERSISTENCE (temporary diagnostic)
        for r in range(2 * Constants.rounds_per_part + 1, 3 * Constants.rounds_per_part + 1):
            p = self.player.in_round(r)

            # overwrite unconditionally
            p.delegate_decision_optional = self.player.delegate_decision_optional

            # force a database write by touching payoff (harmless)
            p.payoff = p.payoff



# -------------------------
#  Results
# -------------------------

class Results(Page):
    def is_displayed(self):
        return self.round_number % Constants.rounds_per_part == 0

    def vars_for_template(self):
        import json

        current_part = Constants.get_part(self.round_number)
        if current_part  == 2 or (current_part == 3 and self.player.delegate_decision_optional):
            is_delegation=False
        else: 
            is_delegation=  self.player.field_maybe_none('delegate_decision_optional')
        #decisions = json.loads(self.player.random_decisions)

        player  = self.player
        rounds_data = []

        for r in range(
                (current_part - 1) * Constants.rounds_per_part + 1,
                current_part     * Constants.rounds_per_part + 1
        ):
            rr         = player.in_round(r)
            my_payoff = rr.payoff
            other = rr.get_others_in_group()[0]
            #allocation = rr.field_maybe_none('allocation') or 0   # 0 if None
            my_choice = rr.field_maybe_none('choice')
            other = rr.get_others_in_group()[0]
            other_choice = other.field_maybe_none('choice')
            #other_delegated = other.field_maybe_none('delegate_decision_optional')
            rounds_data.append({
                'round'     : r - (current_part - 1) * Constants.rounds_per_part,
                #'kept'      : 100 - allocation,
                #'allocated' : allocation,
                #'total'     : 100,
                # NEW (opponent info)
                'my_choice': my_choice,
                'other_choice': other_choice,
                #'other_delegated': other_delegated,
                'payoff': my_payoff,
                #'other_allocation': other.field_maybe_none('allocation'),
                #'other_delegated': other.field_maybe_none('delegate_decision_optional'),
            })
        other = self.player.get_others_in_group()[0]
        print("ME:", self.player.id_in_group, "OTHER:", other.id_in_group)

        return dict(
            current_part = current_part,
            rounds_data  = rounds_data,
            is_delegation = is_delegation,
            payoff = my_payoff
        )


# -------------------------
#  Delegation guessing
# -------------------------

class GuessDelegation(Page):
    form_model = 'player'

    def is_displayed(self):
        # ✅ show ONCE, at end of Part 3
        return self.round_number == 3 * Constants.rounds_per_part

    def get_form_fields(self):
        return [f"guess_round_{i}" for i in range(1, 11)]

    def vars_for_template(self):
        rows = []
        start = 2 * Constants.rounds_per_part + 1  # round 21

        for i in range(1, 11):
            r = start + i - 1
            me = self.player.in_round(r)
            other = me.get_others_in_group()[0]

            rows.append({
                "round": i,
                "my_choice": me.field_maybe_none("choice"),
                "other_choice": other.field_maybe_none("choice"),
                "field_name": f"guess_round_{i}",
            })

        return {"rows": rows}

    def before_next_page(self):
        start = 2 * Constants.rounds_per_part + 1  # round 21

        for i in range(1, 11):
            r = start + i - 1
            future_player = self.player.in_round(r)

            guess_field = f"guess_round_{i}"
            guess = getattr(self.player, guess_field)

            # ✅ 1. store the per‑round guess explicitly
            setattr(future_player, guess_field, guess)

            # ✅ 2. store unified guess field (used elsewhere)
            future_player.guess_opponent_delegated = guess

            # ✅ 3. compute and ALWAYS store payoff
            other = future_player.get_others_in_group()[0]
            actual = bool(other.field_maybe_none("delegate_decision_optional"))

            future_player.guess_payoff = (
                cu(100) if (guess == 'yes') == actual else cu(0)
            )

        self.participant.vars['guess_submitted'] = True


# -------------------------
#  Debriefing
# -------------------------

class Debriefing(Page):
    def is_displayed(self):
        return  self.round_number == Constants.num_rounds


    def vars_for_template(self):
        import random

        results_by_part = {}

        existing = self.player.field_maybe_none("random_payoff_part")
        if existing is None:
            payoff_part = random.randint(1, 3)
            self.player.random_payoff_part = payoff_part
        else:
            payoff_part = existing

        for part in range(1, 4):
            part_data = []
            total = 0

            for r in range(
                (part - 1) * Constants.rounds_per_part + 1,
                part * Constants.rounds_per_part + 1
            ):
                me = self.player.in_round(r)
                other = me.get_others_in_group()[0]

                part_data.append({
                    "round": r - (part - 1) * Constants.rounds_per_part,
                    "my_choice": me.field_maybe_none("choice"),
                    "other_choice": other.field_maybe_none("choice"),
                    "other_delegated": bool(other.field_maybe_none("delegate_decision_optional")),
                    "payoff": me.payoff,
                })

                total += me.payoff or 0



            results_by_part[part] = {
                "rounds": part_data,
                "total_payoff": total,
            }
        # ==============================
        # ADDITION: Part 4 results table
        # ==============================
        guess_rounds_data = []

        for r in range(
            2 * Constants.rounds_per_part + 1,
            3 * Constants.rounds_per_part + 1
        ):
            me = self.player.in_round(r)
            other = me.get_others_in_group()[0]

            guess_rounds_data.append({
                "round": r - 2 * Constants.rounds_per_part,
                "my_choice": me.field_maybe_none("choice"),
                "other_choice": other.field_maybe_none("choice"),
                "other_delegated": bool(other.field_maybe_none("delegate_decision_optional")),
                "payoff": me.field_maybe_none("payoff"),
            })


        


        # ==============================
        # ADDITION: Guessing game bonus
        # ==============================
        guessing_bonus = 0

        for row in guess_rounds_data:
            guessing_bonus += row["payoff"] or 0

        total_bonus = results_by_part[payoff_part]["total_payoff"] + guessing_bonus
        return {
            "results_by_part": results_by_part,
            "random_payoff_part": payoff_part,
            "total_payoff": results_by_part[payoff_part]["total_payoff"],
            "guess_rounds_data": guess_rounds_data,
            "guessing_bonus": guessing_bonus,
            "total_bonus": total_bonus,
        }


    

class ExitQuestionnaire(Page):
    def error_message(self, values):
        if values.get('part_3_feedback') == 'part_3_other':
            if not values.get('part_3_feedback_other'):
                return "Please specify your reason if you selected 'Other'."
    form_model = 'player'
    form_fields = [
        'gender',           # Male / Female / Non-binary / Prefer not to say
        'age',              # 18 – 100
        'occupation',       # free text ≤ 100 chars
        'ai_use',           # frequency scale
        'task_difficulty',  # difficulty scale
        'part_3_feedback',
        'part_3_feedback_other',
        'part_4_feedback',
        'part_4_feedback_other',
        'feedback',         # optional free text ≤ 1000 chars

    ]

    def is_displayed(self):
        return  self.round_number == Constants.num_rounds


class Thankyou(Page):

    # the Prolific completion link

    def vars_for_template(self):
        prolific_url = 'https://bsky.app/profile/iterrucha.bsky.social'

        return dict(url=prolific_url)
    
    def is_displayed(self): 
        return self.round_number == Constants.num_rounds

""" class SaveData(Page):
    def is_displayed(self):
        return self.round_number == Constants.num_rounds or self.player.is_excluded

    def save_player_data(self):
        import pandas as pd

        rows = []

        for pl in self.player.in_all_rounds():
            other = pl.get_others_in_group()[0]

            part = Constants.get_part(pl.round_number)
            round_in_part = (pl.round_number - 1) % Constants.rounds_per_part + 1

            rows.append({
                # --- Identifiers ---
                "participant_code": pl.participant.code,
                "session_code": pl.session.code,
                "experiment": pl.session.config.get("display_name", ""),
                "prolific_id": pl.field_maybe_none("prolific_id"),

                # --- Structure ---
                "part": part,
                "round_in_part": round_in_part,
                "absolute_round": pl.round_number,

                # --- Decisions ---
                "my_choice": pl.field_maybe_none("choice"),
                "my_delegated": bool(pl.field_maybe_none("delegate_decision_optional")),
                "opponent_choice": other.field_maybe_none("choice"),
                "opponent_delegated": bool(other.field_maybe_none("delegate_decision_optional")),
                "guess_opponent_delegated": pl.field_maybe_none("guess_opponent_delegated"),
                
                # --- Outcome ---
                "payoff": pl.payoff,

                # --- Payment logic ---
                "payoff_part_selected": pl.field_maybe_none("random_payoff_part"),

                # --- Demographics ---
                "gender": pl.field_maybe_none("gender"),
                "age": pl.field_maybe_none("age"),
                "occupation": pl.field_maybe_none("occupation"),
                "ai_use": pl.field_maybe_none("ai_use"),
                "task_difficulty": pl.field_maybe_none("task_difficulty"),
                "feedback": pl.field_maybe_none("feedback"),

                # --- Quality control ---
                "comprehension_attempts": pl.field_maybe_none("comprehension_attempts"),
                "is_excluded": pl.field_maybe_none("is_excluded"),
                
            })

        df = pd.DataFrame(rows)

        # ✅ Forward-fill demographics & static fields
        static_cols = [
            "prolific_id", "gender", "age", "occupation",
            "ai_use", "task_difficulty", "feedback",
            "payoff_part_selected", "comprehension_attempts", "is_excluded"
        ]
        df[static_cols] = df[static_cols].ffill().bfill()

        prolific_id = df["prolific_id"].iloc[0]

        path = settings.data_path
        df.to_csv(path + f"{prolific_id}.csv", index=False)


            
    def before_next_page(self):
        # Save player data before moving to the next page
        print("S Round number:  ,",self.round_number)

        if self.round_number == Constants.num_rounds:
            #print("Round number: ,",self.round_number)
            self.save_player_data()

 """
#new pages
class BotDetection(Page):
    template_name = "dictator_game/templates/dictator_game/BotDetection.html"

    def is_displayed(self):
        if self.round_number != 1:
            return False
        pid = self.player.field_maybe_none("prolific_id")
        return pid == "1234567890GenerativeAI4U"
    
class MainInstructions(Page):
    template_name = "dictator_game/templates/dictator_game/MainInstructions.html"

    def is_displayed(self):
        return self.round_number == 1
    
class InstructionsNoDelegation(Page):
    template_name = "dictator_game/templates/dictator_game/InstructionsNoDelegation.html"

    def is_displayed(self):
        return (
            Constants.get_part(self.round_number) == 2
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )
    
class InstructionsDelegation(Page):
    def is_displayed(self):
        return (
            Constants.get_part(self.round_number) == 1
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )
#changes are made
class DecisionNoDelegation(Page):
    template_name = "dictator_game/templates/dictator_game/DecisionNoDelegation.html"
    form_model = "player"
    form_fields = ["choice"]

    def is_displayed(self):
        return Constants.get_part(self.round_number) == 2

    def vars_for_template(self):
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        return {
            "round_number": round_in_part,
            "current_part": 2,
        }

    def before_next_page(self):
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        field_name = f"human_decision_no_delegation_round_{round_in_part}"

        # ✅ store on THIS round
        setattr(self.player, field_name, self.player.choice)

        # ✅ also store centrally on round 11 (or round 1 of part 2)
        anchor = self.player.in_round(Constants.rounds_per_part + 1)
        setattr(anchor, field_name, self.player.choice)
        round_in_part = (self.round_number - 1) % Constants.rounds_per_part + 1
        field_name = f"human_decision_no_delegation_round_{round_in_part}"

        setattr(self.player, field_name, self.player.choice)

        print(
            "HUMAN DECISION SAVED:",
            "abs round =", self.round_number,
            "field =", field_name,
            "value =", self.player.choice
        )
    
class InstructionsOptional(Page):
    template_name = "dictator_game/templates/dictator_game/InstructionsOptional.html"

    def is_displayed(self):
        return (
            Constants.get_part(self.round_number) == 3
            and (self.round_number - 1) % Constants.rounds_per_part == 0
        )
    
class InstructionsGuessingGame(Page):
    template_name = "dictator_game/templates/dictator_game/InstructionsGuessingGame.html"

    def is_displayed(self):
        return self.round_number == 30
    
class DecisionsGuessingGame(Page):
    template_name = "dictator_game/templates/dictator_game/DecisionsGuessingGame.html"
    form_model = "player"
    form_fields = ["guess_opponent_delegated"]

    def is_displayed(self):
        return self.round_number == Constants.num_rounds
    
class ResultsGuess(Page):
    def is_displayed(self):
        return (
            self.round_number == Constants.num_rounds
            and self.participant.vars.get('guess_submitted', False)
        )

    def is_displayed(self):
        return self.round_number == 3 * Constants.rounds_per_part

    def vars_for_template(self):
        rows = []

        for r in range(
            2 * Constants.rounds_per_part + 1,
            3 * Constants.rounds_per_part + 1
        ):
            me = self.player.in_round(r)
            other = me.get_others_in_group()[0]

            guess = me.field_maybe_none("guess_opponent_delegated")

            if guess is None:
                my_decision = "No guess"
            elif guess == 'yes':
                my_decision = "Delegated"
            else:
                my_decision = "Did not delegate"

            rows.append({
                "round": r - 2 * Constants.rounds_per_part,
                "my_decision": my_decision,
                "other_decision": (
                    "Delegated"
                    if other.field_maybe_none("delegate_decision_optional")
                    else "Did not delegate"
                ),
                "earnings": me.guess_payoff,
            })

        return {"rows": rows}
# -------------------------
#  Page Sequence
# -------------------------

page_sequence = [
    InformedConsent,
    #BotDetection,
    #MainInstructions,
    #ComprehensionTest,
    #FailedTest,
    InstructionsDelegation,
    InstructionsNoDelegation,

    DecisionNoDelegation,
    WaitForGroup,
    Results,
    InstructionsOptional,
    DelegationDecision,
    AgentProgramming,
    
    InstructionsGuessingGame,
    GuessDelegation,
    ResultsGuess,
    Debriefing,
    ExitQuestionnaire,
    Thankyou,
]