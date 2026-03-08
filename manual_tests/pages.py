from otree.api import *
import pprint


class MyPage(Page):

    def vars_for_template(self):

        # PARAMETERS
        N_players = 5   # >= 3
        N_rounds = 10

        # Initialize assignments
        player_assignments = {player: [] for player in range(1, N_players + 1)}

        # Round-robin opponent assignment
        for r in range(1, N_rounds + 1):
            opponents = list(range(1, N_players + 1))

            for player in range(1, N_players + 1):
                # Find the next opponent (skip self)
                for i in range(1, N_players):
                    opponent = opponents[(player + i + r - 1) % N_players]
                    if opponent != player:
                        player_assignments[player].append((opponent, r))
                        break

        # VERIFY: at least 2 unique opponents per player
        for player in player_assignments:
            unique_opponents = set(opponent for (opponent, _) in player_assignments[player])
            assert len(unique_opponents) >= min(2, N_players - 1), (
                f"Player {player} has fewer than 2 unique opponents!"
            )

        # VERIFY: total number of matches
        all_matches = [
            match
            for player in player_assignments
            for match in player_assignments[player]
        ]
        assert len(all_matches) == N_players * N_rounds, "Not all matches assigned!"

        # PRINT TO SERVER LOG (useful for debugging)
        print("\nPLAYER ASSIGNMENTS")
        for player in range(1, N_players + 1):
            print(f"Player {player}: {player_assignments[player]}")
        print(f"Total matches: {len(all_matches)}\n")

        # Send data to template
        return dict(
            assignments=player_assignments,
            total_matches=len(all_matches),
            N_players=N_players,
            N_rounds=N_rounds,
            pretty_assignments=pprint.pformat(player_assignments),
        )


page_sequence = [MyPage]