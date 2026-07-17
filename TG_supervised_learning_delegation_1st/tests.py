"""Bot tests for TG_supervised_learning_delegation_1st."""

import os

from otree.api import Bot

from pages_classes.tg_v2_pages import TgV2HumanDecisionsFirst, TgV2HumanDecisionsSecond
from shared.tg_player_bot import make_tg_player_bot_play_round

from . import pages

os.environ.setdefault("OTREE_SKIP_CSRF", "1")


class PlayerBot(Bot):
    play_round = make_tg_player_bot_play_round(
        treatment="supervised",
        pages_module=pages,
        human_first_page=TgV2HumanDecisionsFirst,
        human_second_page=TgV2HumanDecisionsSecond,
        agent_first_page=pages.TgSupervisedAgentFirst,
        agent_second_page=pages.TgSupervisedAgentSecond,
    )
