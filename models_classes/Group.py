"""Shared Group payoff logic (callable from each app's ``Group.set_payoffs``)."""

import importlib

from otree.api import cu


def set_payoffs_pd_batch_group(group):
    """
    Standard PD batch payoffs: same released ``matching_group_id``, round-robin opponent,
    ``Constants.PD_PAYOFFS``. Otherwise payoff 0. Resolves ``Constants`` and ``get_opponent_in_round``
    from the app's ``models`` module (the same module that defines ``group``).
    """
    m = importlib.import_module(type(group).__module__)
    Constants = m.Constants
    get_opponent_in_round = m.get_opponent_in_round

    players = group.get_players()
    if len(players) == 1:
        players[0].payoff = cu(0)
        return
    if len(players) >= 3:
        gids = [p.participant.vars.get("matching_group_id", -1) for p in players]
        if all(g >= 0 for g in gids) and len(set(gids)) == 1:
            rnd = group.round_number
            for p in players:
                opp = get_opponent_in_round(p, rnd)
                if opp is None:
                    p.payoff = cu(0)
                    continue
                c1 = p.field_maybe_none("choice")
                c2 = opp.field_maybe_none("choice")
                if c1 is None or c2 is None:
                    p.payoff = cu(0)
                    continue
                pay = Constants.PD_PAYOFFS.get((c1, c2))
                p.payoff = cu(pay[0]) if pay is not None else cu(0)
            return
        for p in players:
            p.payoff = cu(0)
        return
    players[0].payoff = cu(0)
    if len(players) > 1:
        for p in players[1:]:
            p.payoff = cu(0)