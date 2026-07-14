"""Minimal oTree app to inspect TG sessions already stored in the database."""

from otree.api import *


class Constants(BaseConstants):
    name_in_url = "tg_session_inspector"
    players_per_group = None
    # Enough rounds to re-filter / rescan without ending the inspector session.
    num_rounds = 50


class Subsession(BaseSubsession):
    pass


class Group(BaseGroup):
    pass


class Player(BasePlayer):
    selected_session_code = models.StringField(
        label="TG session to inspect",
        blank=True,
    )
    filter_date_from = models.StringField(
        label="From date (YYYY-MM-DD)",
        blank=True,
    )
    filter_date_to = models.StringField(
        label="To date (YYYY-MM-DD)",
        blank=True,
    )
    # SessionSelect: "filter" | "scan"
    select_action = models.StringField(blank=True)
    # InspectSession: "rescan" | "back" | "done" | "apply_filters"
    inspect_action = models.StringField(blank=True)
    # On InspectSession only (reused): filter_date_from = P from, filter_date_to = P to,
    # select_action = prolific id. On SessionSelect they are date/action fields.
