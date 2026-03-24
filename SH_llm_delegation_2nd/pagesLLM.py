from otree.api import *
from .models import Constants, initialize_assistant
import json
import re

class ChatGPTPage(Page):

    """ Page where users interact with ChatGPT in real-time """
    form_model = 'player'  # ✅ Required for form submission
    form_fields = []


    def is_displayed(self):
        """ Ensure ChatGPTPage runs for each round in the part """
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1  # ✅ Get round within part

        # ✅ Show ChatGPTPage for each round in Part 2 or Part 3 (if delegation is chosen)
        return (current_part == 2 or (current_part == 3 and self.player.delegate_decision_optional)) and (display_round -1) % Constants.rounds_per_part ==0
    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        return {
            'current_part' : current_part,
         }
        
    def before_next_page(self):
        chatgpt_final_response=self.get_final_assistant_response()
        #c$#"
        self.save_allocations_to_future_rounds(chatgpt_final_response)
        print('Saved Allocations from AI Assistant')
        
    def get_final_assistant_response(self):

        
            conversation = json.loads(self.player.conversation_history)
            pattern = r'^(\d{1,3},\s*){9}\d{1,3}$'

            last_assistant_message = next(
                (
                    msg["content"] 
                    for msg in reversed(conversation) 
                    if msg["role"] == "assistant" and re.match(pattern, msg["content"].strip())
                ),
                None
            )

            print("Last LLM Message:", last_assistant_message)
            if last_assistant_message != None: 
                print('Re Matched')
                return last_assistant_message
            else: 
                print('No pattern match GPT message found, Sending Sample')
                return "10,10,10,10,10,10,10,10,10,10"

    def save_allocations_to_future_rounds(self, chatgpt_final_response):
    
        allocation_values = chatgpt_final_response.split(',')  # ✅ Split ChatGPT response into list
        print('Last GPT Response: ',allocation_values)
        try:
            # ✅ Ensure we have exactly 10 allocations (Rounds 10 to 20)
            if len(allocation_values) < 10:
                print("⚠️ ChatGPT did not return 10 allocations, skipping storage.")
                return

            round_number=self.round_number
            print('Ongoing Round: ',round_number)
            for i in range(1,11):  # ✅ Loop for 10 rounds (rounds 10-20)
                # ✅ Fetch player object for the future round
                future_player = self.player.in_round(round_number)
                self.round_number=round_number

                # ✅ Store allocation in the correct round
                future_player.allocation = int(allocation_values[i-1].strip())
                print(f"✅ Saved allocation {future_player.allocation} for Round {round_number}")
                round_number = round_number + 1

        except (ValueError, IndexError):
            print("⚠️ Error: ChatGPT response is not formatted correctly, skipping.")

    def live_method(self, data):
        chatbot_assistant=initialize_assistant(self)

        if self.assistant_id:

            """ Handles real-time chat interaction via WebSockets """
            self.participant.vars['alert_message']="" #test alert removal
            user_message = data['message']  # Get user input
            print("recieved user message")
            # Load existing conversation history
            #conversation = json.loads(self.conversation_history)
            conversation = [{"role": "system", "content": "Hi! I am your allocation assistant."}]
            # Append user's message
            conversation.append({"role": "user", "content": user_message})

            # Get AI response
            print("Sending user message to CHATGPT")
            chatgpt_response = chatbot_assistant.send_message(user_message)
            print('ChatGPT response:',chatgpt_response)
            allocation_values = chatgpt_response.split(',')

            conversation.append( {"role": "assistant", "content": chatgpt_response})
            # Save conversation history
            self.conversation_history = json.dumps(conversation)

            # Send response back to the frontend
            #send_rec_msg={self.id_in_group: {"message": user_message, "response": chatgpt_response}}
            #print('Sending back the msg to HTML: ',chatgpt_response)
            return {self.id_in_group: {"response": chatgpt_response}}
    

class InformedConsent(Page):
    form_model = 'player'
    form_fields = ['prolific_id']
    def is_displayed(self):
        return self.round_number == 1  # Show only once at the beginning


class Introduction(Page):
    def is_displayed(self):
        return self.round_number == 1  # Show only once at the beginning


class ComprehensionTest(Page):
    form_model = 'player'
    form_fields = ['q1', 'q2', 'q3', 'q4', 'q5', 'q6', 'q7', 'q8', 'q9', 'q10']

    def is_displayed(self):
        return not self.player.is_excluded and self.round_number == 1

    def error_message(self, values):
        correct_answers = {
            'q1': 'b',
            'q2': 'c',
            'q3': 'b',
            'q4': 'd',
            'q5': 'a',
            'q6': 'a',
            'q7': 'b',
            'q8': 'a',
        }

        incorrect = [
            q for q, correct in correct_answers.items()
            if values.get(q) != correct or not values.get(q)
        ]

        if incorrect:
            self.player.comprehension_attempts += 1

            if self.player.comprehension_attempts == 1:
                 return f"You have failed questions: {', '.join(incorrect)}. You now only have 2 attempts"
            
            elif self.player.comprehension_attempts == 2:
                 return f"You have failed questions: {', '.join(incorrect)}. You now only have 1 attempt"
            
            elif self.player.comprehension_attempts == 1:
                 return f"You have failed questions: {', '.join(incorrect)}. You now only have last attempt"
            else:
                self.player.is_excluded = True




class FailedTest(Page):
    def is_displayed(self):
        return self.player.is_excluded


# -------------------------
#  Per-Part Instructions
# -------------------------

class Instructions(Page):
    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)

        return  (self.round_number - 1) % Constants.rounds_per_part == 0

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        return {
            'current_part': current_part,
            'incorrect_answers': self.player.incorrect_answers,

        }


# -------------------------
#  Agent Programming
# -------------------------

#  Decision Making
# -------------------------

class Decision(Page):
    form_model = 'player'
    form_fields = ['allocation']
    #timeout_seconds = 20

 

    def is_displayed(self):
        current_part = Constants.get_part(self.round_number)
        # Show Decision page only if not in Part 2 and not using optional delegation in Part 3
        #return not (current_part == 2 or (current_part == 3 and self.player.delegate_decision_optional))
        return not (current_part == 2 or (current_part == 3 and self.player.delegate_decision_optional))
    

    def vars_for_template(self):
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1
        allocation = 0
       
        if current_part == 2:
            current_player = self.player.in_round(display_round)
            allocation=current_player.allocation
        elif current_part == 3 and self.player.delegate_decision_optional:
             allocation = self.player.get_agent_decision_optional(display_round)
        
        elif current_part ==3 and not self.player.delegate_decision_optional:
            current_player = self.player.in_round(display_round)
            allocation=current_player.allocation
        return {
            'round_number': display_round,
            'current_part': current_part,
            'decision_mode': (
                "agent" if (current_part == 2 or (current_part == 3 and self.player.delegate_decision_optional)) else "manual"
            ),
            'player_allocation': allocation,
            'alert_message': self.participant.vars.get('alert_message', ""),
                }

    def before_next_page(self):
        import json
        import random

 
        current_part = Constants.get_part(self.round_number)
        display_round = (self.round_number - 1) % Constants.rounds_per_part + 1

        if current_part == 1  :  # Part 1 logic or Part 3 with manual with manual decisions and timer
            if self.timeout_happened or self.player.allocation is None:
                # Assign random allocation if timer expires
                self.player.allocation = random.randint(0, 100)
                self.participant.vars['alert_message'] = (
                    f"You did not make a choice, so {self.player.allocation} was chosen for you. "
                )
                self.player.random_decisions = True
            else:
                # Clear the alert message if no timeout occurred
                self.participant.vars['alert_message'] = None
                self.player.random_decisions = False
            # Update decisions for the current round



        elif current_part == 2:  # Mandatory delegation
            self.player.allocation = self.player.get_agent_decision_mandatory(display_round)
            self.participant.vars['alert_message'] = ""
            self.player.random_decisions = True

        elif current_part == 3 and self.player.delegate_decision_optional:  # Optional delegation
            self.player.allocation = self.player.get_agent_decision_optional(display_round)
            self.participant.vars['alert_message'] = ""
            self.player.random_decisions = True
        
        elif current_part == 3 and not self.player.delegate_decision_optional:  # Optional delegation
            #self.player.allocation = self.player.get_agent_decision_optional(display_round)
            if self.timeout_happened or self.player.allocation is None:
                # Assign random allocation if timer expires
                self.player.allocation = random.randint(0, 100)
                self.participant.vars['alert_message'] = (
                    f"You did not make a choice, so {self.player.allocation} was chosen for you. "
                )
                self.player.random_decisions = True

            else:
                # Clear the alert message if no timeout occurred
                self.participant.vars['alert_message'] = ''
                self.player.random_decisions = False
            



        print(f"round:{self.round_number}  self.player.allocation: {self.player.allocation}")


# -------------------------
#  Delegation Decision
# -------------------------

class DelegationDecision(Page):
    form_model = 'player'
    form_fields = ['delegate_decision_optional']

    def is_displayed(self):
        # Show only at the start of Part 3

        return Constants.get_part(self.round_number) == 3 and (self.round_number - 1) % Constants.rounds_per_part == 0

    def before_next_page(self):
        # Save the decision for all rounds in Part 3
        if Constants.get_part(self.round_number) == 3:
            part_rounds = self.player.in_rounds(
                (Constants.get_part(self.round_number) - 1) * Constants.rounds_per_part + 1,
                Constants.get_part(self.round_number) * Constants.rounds_per_part
            )
            for p in part_rounds:
                p.delegate_decision_optional = self.player.delegate_decision_optional



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
            allocation = rr.field_maybe_none('allocation') or 0   # 0 if None
            rounds_data.append({
                'round'     : r - (current_part - 1) * Constants.rounds_per_part,
                'kept'      : 100 - allocation,
                'allocated' : allocation,
                'total'     : 100,
            })

        return dict(
            current_part = current_part,
            rounds_data  = rounds_data,
            is_delegation = is_delegation,
        )


# -------------------------
#  Debriefing
# -------------------------


class Debriefing(Page):
    def is_displayed(self):
        return  self.round_number == Constants.num_rounds


    def vars_for_template(self):
        import json
        import random

        results_by_part = {}
        totals_by_part= {}

        round_number=self.round_number
        random_payoff_part=random.randint(1,3)

        # Loop through parts (1, 2, 3)
        for part in range(1, 4):
            part_data = []
            for round_number in range(
                (part - 1) * Constants.rounds_per_part + 1,
                part * Constants.rounds_per_part + 1
            ):
                round_result = self.player.in_round(round_number)
                part_data.append({
                    "round": round_number,
                    "kept": 100 - (round_result.field_maybe_none('allocation') or 0),
                    "allocated": round_result.field_maybe_none('allocation')or 0,
                    "decision" : round_result.field_maybe_none('random_decisions'),
                })

            results_by_part[part] = part_data
            total_kept = sum(item["kept"] for item in part_data)
            total_allocated = sum(item["allocated"] for item in part_data)
            totals_by_part[part] = {
            "total_kept": total_kept,
        }


        # Check if agent allocation was chosen in part 3
        agent_allocation_chosen = self.player.field_maybe_none('delegate_decision_optional')
        if self.player.field_maybe_none('random_payoff_part') == None: 
            random_payoff_part=self.random_payoff_selection()
            self.player.random_payoff_part=random_payoff_part
        else: 
            random_payoff_part=self.player.random_payoff_part

        

        payoff_data=results_by_part[self.player.random_payoff_part]
        total_kept,total_allocated=self.calculate_total_payoff(payoff_data)


        return {
            'results_by_part': results_by_part,
            'totals_by_part': totals_by_part,

            'totals_by_1': totals_by_part[1]['total_kept'],
            'totals_by_2': totals_by_part[2]['total_kept'],
            'totals_by_3': totals_by_part[3]['total_kept'],
            'agent_allocation_chosen': agent_allocation_chosen,
            'random_payoff_part': random_payoff_part,
            'total_kept' : total_kept,
            'payoff_cents' : (int(total_kept) + 5) // 10,
            'total_allocated' : total_allocated
               }
    

    def random_payoff_selection(self): 
        import random

        round_number=self.round_number
        random_payoff_part=random.randint(1,3)
        return random_payoff_part

    def calculate_total_payoff(self, part_data): 
        total_kept=0
        total_allocated=0
        for round in part_data: 
                total_kept=total_kept+round["kept"]
                total_allocated=total_allocated+round["allocated"]
        
        return total_kept,total_allocated

class ExitQuestionnaire(Page):
    form_model = 'player'
    form_fields = [
        'gender',           # Male / Female / Non-binary / Prefer not to say
        'age',              # 18 – 100
        'occupation',       # free text ≤ 100 chars
        'ai_use',           # frequency scale
        'task_difficulty',  # difficulty scale
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



# -------------------------
#  Page Sequence
# -------------------------
#page_sequence=[ChatGPTPage]

page_sequence = [
    InformedConsent,        # Only at the beginning
    Introduction,           # Only at the beginning
    ComprehensionTest,      # Only at the beginning
    FailedTest,             # If excluded after failing comprehension test
    Instructions,           # Once at the start of each part
    DelegationDecision,     # At the start of Part 3 to choose delegation
    ChatGPTPage,            # ChatGPTPage for Part 2 or optional delegation in Part 3
    Decision,               # Decision page for Part 1 and manual decisions in Part 3
    Results,                # Reusable for all parts
    Debriefing,             # At the end or if excluded
    ExitQuestionnaire,
    Thankyou,
]