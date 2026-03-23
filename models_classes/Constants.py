"""Shared base constants for PD apps."""

from otree.api import BaseConstants


class ConstantsBase(BaseConstants):
    """Use ``@classmethod`` so subclasses' ``rounds_per_part`` and ``DELEGATION_FIRST`` apply."""

    @classmethod
    def get_part(cls, round_number):
        return (round_number - 1) // cls.rounds_per_part + 1

    @classmethod
    def part_no_delegation(cls):
        return 2 if cls.DELEGATION_FIRST else 1

    @classmethod
    def part_delegation(cls):
        return 1 if cls.DELEGATION_FIRST else 2

    @classmethod
    def is_mandatory_delegation_round(cls, round_number):
        part = cls.get_part(round_number)
        if cls.DELEGATION_FIRST:
            return part == 1
        return part == 2

