"""
One-off sync: copy PD app logic into SD / SH counterparts.
Preserves each target's name_in_url; sets Snowdrift (SD) / Stag-Hunt (SH) PD_PAYOFFS.
Run from repo root: python _sync_sd_sh_from_pd.py
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PD_PAYOFFS_BLOCK = """    PD_PAYOFFS = {
        ('A', 'A'): (70, 70),
        ('A', 'B'): (0, 100),
        ('B', 'A'): (100, 0),
        ('B', 'B'): (30, 30),
    }"""

SD_PAYOFFS_BLOCK = """    PD_PAYOFFS = {
        ('A', 'A'): (70, 70),
        ('A', 'B'): (30, 100),
        ('B', 'A'): (100, 30),
        ('B', 'B'): (0, 0),
    }"""

SH_PAYOFFS_BLOCK = """    PD_PAYOFFS = {
        ('A', 'A'): (100, 100),
        ('A', 'B'): (0, 50),
        ('B', 'A'): (50, 0),
        ('B', 'B'): (50, 50),
    }"""

# (pd_folder, sd_folder, sd_name_in_url, sh_folder, sh_name_in_url)
APP_PAIRS = [
    (
        "PD_supervised_learning_delegation_1st",
        "SD_supervised_learning_delegation_1st",
        "exp_game313",
        "SH_supervised_learning_delegation_1st",
        "exp_game213",
    ),
    (
        "PD_supervised_learning_delegation_2nd",
        "SD_supervised_learning_delegation_2nd",
        "exp_game323",
        "SH_supervised_learning_delegation_2nd",
        "exp_game223",
    ),
    (
        "PD_rule_based_delegation_1st",
        "SD_rule_based_delegation_1st",
        "exp_game311",
        "SH_rule_based_delegation_1st",
        "exp_game211",
    ),
    (
        "PD_rule_based_delegation_2nd",
        "SD_rule_based_delegation_2nd",
        "exp_game321",
        "SH_rule_based_delegation_2nd",
        "exp_game221",
    ),
    (
        "PD_llm_delegation_1st",
        "SD_llm_delegation_1st",
        "exp_game312",
        "SH_llm_delegation_1st",
        "exp_game212",
    ),
    (
        "PD_llm_delegation_2nd",
        "SD_llm_delegation_2nd",
        "exp_game322",
        "SH_llm_delegation_2nd",
        "exp_game222",
    ),
    (
        "PD_goal_oriented_delegation_1st",
        "SD_goal_oriented_delegation_1st",
        "exp_game341",
        "SH_goal_oriented_delegation_1st",
        "exp_game241",
    ),
    (
        "PD_goal_oriented_delegation_2nd",
        "SD_goal_oriented_delegation_2nd",
        "exp_game342",
        "SH_goal_oriented_delegation_2nd",
        "exp_game242",
    ),
]


def replace_name_in_url(text: str, new_url: str) -> str:
    return re.sub(
        r"^(\s*name_in_url\s*=\s*)'[^']+'(.*)$",
        lambda m: f"{m.group(1)}'{new_url}'{m.group(2) or ''}",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def patch_models(text: str, name_in_url: str, payoff_block: str) -> str:
    if PD_PAYOFFS_BLOCK not in text:
        raise ValueError("Expected PD PD_PAYOFFS block not found in models.py")
    text = text.replace(PD_PAYOFFS_BLOCK, payoff_block, 1)
    return replace_name_in_url(text, name_in_url)


def copy_file(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def sync_supervised(pd: str, target: str, name_in_url: str, payoff_block: str) -> None:
    pd_p = ROOT / pd
    tg_p = ROOT / target
    # models
    raw = (pd_p / "models.py").read_text(encoding="utf-8")
    write_text(tg_p / "models.py", patch_models(raw, name_in_url, payoff_block))
    # pages
    pg = (pd_p / "pages.py").read_text(encoding="utf-8").replace(pd, target)
    write_text(tg_p / "pages.py", pg)
    # supervisedLearning.py — swap app prefix in template_name only
    sl = (pd_p / "supervisedLearning.py").read_text(encoding="utf-8")
    sl = sl.replace(pd, target)
    write_text(tg_p / "supervisedLearning.py", sl)
    # template (identical markup; path differs only on disk)
    tsrc = pd_p / "templates" / pd / "supervisedLearning.html"
    tdst = tg_p / "templates" / target / "supervisedLearning.html"
    copy_file(tsrc, tdst)


def sync_rule_based(pd: str, target: str, name_in_url: str, payoff_block: str) -> None:
    pd_p = ROOT / pd
    tg_p = ROOT / target
    raw = (pd_p / "models.py").read_text(encoding="utf-8")
    write_text(tg_p / "models.py", patch_models(raw, name_in_url, payoff_block))
    pg = (pd_p / "pages.py").read_text(encoding="utf-8").replace(pd, target)
    write_text(tg_p / "pages.py", pg)
    rb_path = pd_p / "ruleBased.py"
    if rb_path.exists():
        rb = rb_path.read_text(encoding="utf-8").replace(pd, target)
        write_text(tg_p / "ruleBased.py", rb)
    tsrc = pd_p / "templates" / pd / "AgentProgramming.html"
    tdst = tg_p / "templates" / target / "AgentProgramming.html"
    copy_file(tsrc, tdst)


def sync_llm(pd: str, target: str, name_in_url: str, payoff_block: str) -> None:
    pd_p = ROOT / pd
    tg_p = ROOT / target
    raw = (pd_p / "models.py").read_text(encoding="utf-8")
    write_text(tg_p / "models.py", patch_models(raw, name_in_url, payoff_block))
    pg = (pd_p / "pages.py").read_text(encoding="utf-8").replace(pd, target)
    write_text(tg_p / "pages.py", pg)
    copy_file(pd_p / "mistralassistant.py", tg_p / "mistralassistant.py")
    tsrc = pd_p / "templates" / pd / "MistralPage.html"
    tdst = tg_p / "templates" / target / "MistralPage.html"
    copy_file(tsrc, tdst)
    if (pd_p / "mistralPage.py").exists():
        cg = (pd_p / "mistralPage.py").read_text(encoding="utf-8").replace(pd, target)
        write_text(tg_p / "mistralPage.py", cg)


def sync_goal(pd: str, target: str, name_in_url: str, payoff_block: str) -> None:
    pd_p = ROOT / pd
    tg_p = ROOT / target
    raw = (pd_p / "models.py").read_text(encoding="utf-8")
    write_text(tg_p / "models.py", patch_models(raw, name_in_url, payoff_block))
    pg = (pd_p / "pages.py").read_text(encoding="utf-8").replace(pd, target)
    write_text(tg_p / "pages.py", pg)
    go = (pd_p / "goalOriented.py").read_text(encoding="utf-8").replace(pd, target)
    write_text(tg_p / "goalOriented.py", go)
    tsrc = pd_p / "templates" / pd / "goalOriented.html"
    tdst = tg_p / "templates" / target / "goalOriented.html"
    copy_file(tsrc, tdst)


def main() -> None:
    for pd_name, sd_name, sd_url, sh_name, sh_url in APP_PAIRS:
        if "supervised_learning" in pd_name:
            sync_supervised(pd_name, sd_name, sd_url, SD_PAYOFFS_BLOCK)
            sync_supervised(pd_name, sh_name, sh_url, SH_PAYOFFS_BLOCK)
        elif "rule_based" in pd_name:
            sync_rule_based(pd_name, sd_name, sd_url, SD_PAYOFFS_BLOCK)
            sync_rule_based(pd_name, sh_name, sh_url, SH_PAYOFFS_BLOCK)
        elif "llm_delegation" in pd_name:
            sync_llm(pd_name, sd_name, sd_url, SD_PAYOFFS_BLOCK)
            sync_llm(pd_name, sh_name, sh_url, SH_PAYOFFS_BLOCK)
        elif "goal_oriented" in pd_name:
            sync_goal(pd_name, sd_name, sd_url, SD_PAYOFFS_BLOCK)
            sync_goal(pd_name, sh_name, sh_url, SH_PAYOFFS_BLOCK)
        else:
            raise RuntimeError(pd_name)
        print("OK", pd_name, "->", sd_name, ",", sh_name)


if __name__ == "__main__":
    main()
