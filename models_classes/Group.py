"""Shared Group payoff logic (callable from each app's ``Group.set_payoffs``)."""

import importlib

from otree.api import cu


def set_payoffs_pd_batch_group(group):
    """
    Standard PD batch payoffs: same released ``matching_group_id``, round-robin opponent,
    ``Constants.PD_PAYOFFS``. Leaves payoffs unset when not matched or choices missing.
    """
    m = importlib.import_module(type(group).__module__)
    Constants = m.Constants
    get_opponent_in_round = m.get_opponent_in_round

    players = group.get_players()
    if len(players) == 1:
        return
    if len(players) >= 3:
        gids = [p.participant.vars.get("matching_group_id", -1) for p in players]
        if all(g >= 0 for g in gids) and len(set(gids)) == 1:
            rnd = group.round_number
            for p in players:
                opp = get_opponent_in_round(p, rnd)
                if opp is None:
                    continue
                c1 = p.field_maybe_none("choice")
                c2 = opp.field_maybe_none("choice")
                if c1 is None or c2 is None:
                    continue
                pay = Constants.PD_PAYOFFS.get((c1, c2))
                if pay is not None:
                    p.payoff = cu(pay[0])
            return
        return
    return


def set_payoffs_tg_batch_group(group):
    """TG sequential payoffs for a released batch group (see ``shared.tg_payoffs``)."""
    from shared.tg_payoffs import set_payoffs_tg_batch_group as _impl

    _impl(group)
