"""Shared Subsession helpers (not ORM subclasses — oTree cannot inherit Subsession across packages)."""


def creating_session_mark_unmatched(subsession):
    """Round 1: set ``matching_group_id = -1`` for every player (not yet released to a batch)."""
    if subsession.round_number == 1:
        for p in subsession.get_players():
            p.participant.vars["matching_group_id"] = -1