from os import environ

# Enable SQLite WAL (Write-Ahead Logging) for faster writes when using SQLite locally.
# WAL does not apply to PostgreSQL (e.g. on Clever Cloud).
def _enable_sqlite_wal(sender, connection, **kwargs):
    if connection.vendor == 'sqlite3':
        cursor = connection.cursor()
        cursor.execute('PRAGMA journal_mode=WAL')
        cursor.execute('PRAGMA synchronous=NORMAL')  # faster than FULL, still safe

try:
    from django.db.backends.signals import connection_created
    connection_created.connect(_enable_sqlite_wal)
except Exception:
    pass

SESSION_CONFIGS = [
    dict(
        name='PD_goal_oriented_delegation_1st',
        display_name='PD_goal_oriented_delegation_1st',
        app_sequence=['PD_goal_oriented_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_goal_oriented_delegation_2nd',
        display_name='PD_goal_oriented_delegation_2nd',
        app_sequence=['PD_goal_oriented_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_llm_delegation_1st',
        display_name='PD_llm_delegation_1st',
        app_sequence=['PD_llm_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_llm_delegation_2nd',
        display_name='PD_llm_delegation_2nd',
        app_sequence=['PD_llm_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_rule_based_delegation_1st',
        display_name='PD_rule_based_delegation_1st',
        app_sequence=['PD_rule_based_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_rule_based_delegation_2nd',
        display_name='PD_rule_based_delegation_2nd',
        app_sequence=['PD_rule_based_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_rule_based_delegation_2nd_with_bots',
        display_name='PD_rule_based_delegation_2nd_with_bots',
        app_sequence=['PD_rule_based_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=True,
    ),
    dict(
        name='PD_supervised_learning_delegation_1st',
        display_name='PD_supervised_learning_delegation_1st',
        app_sequence=['PD_supervised_learning_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='PD_supervised_learning_delegation_2nd',
        display_name='PD_supervised_learning_delegation_2nd',
        app_sequence=['PD_supervised_learning_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SD_goal_oriented_delegation_1st',
        display_name='SD_goal_oriented_delegation_1st',
        app_sequence=['SD_goal_oriented_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SD_goal_oriented_delegation_2nd',
        display_name='SD_goal_oriented_delegation_2nd',
        app_sequence=['SD_goal_oriented_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SD_llm_delegation_1st',
        display_name='SD_llm_delegation_1st',
        app_sequence=['SD_llm_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SD_llm_delegation_2nd',
        display_name='SD_llm_delegation_2nd',
        app_sequence=['SD_llm_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SD_supervised_learning_delegation_1st',
        display_name='SD_supervised_learning_delegation_1st',
        app_sequence=['SD_supervised_learning_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SD_supervised_learning_delegation_2nd',
        display_name='SD_supervised_learning_delegation_2nd',
        app_sequence=['SD_supervised_learning_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_goal_oriented_delegation_1st',
        display_name='SH_goal_oriented_delegation_1st',
        app_sequence=['SH_goal_oriented_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_goal_oriented_delegation_2nd',
        display_name='SH_goal_oriented_delegation_2nd',
        app_sequence=['SH_goal_oriented_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_llm_delegation_1st',
        display_name='SH_llm_delegation_1st',
        app_sequence=['SH_llm_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_llm_delegation_2nd',
        display_name='SH_llm_delegation_2nd',
        app_sequence=['SH_llm_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_rule_based_delegation_1st',
        display_name='SH_rule_based_delegation_1st',
        app_sequence=['SH_rule_based_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_rule_based_delegation_2nd',
        display_name='SH_rule_based_delegation_2nd',
        app_sequence=['SH_rule_based_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_supervised_learning_delegation_1st',
        display_name='SH_supervised_learning_delegation_1st',
        app_sequence=['SH_supervised_learning_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='SH_supervised_learning_delegation_2nd',
        display_name='SH_supervised_learning_delegation_2nd',
        app_sequence=['SH_supervised_learning_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_goal_oriented_delegation_1st',
        display_name='TG_goal_oriented_delegation_1st',
        app_sequence=['TG_goal_oriented_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_goal_oriented_delegation_2nd',
        display_name='TG_goal_oriented_delegation_2nd',
        app_sequence=['TG_goal_oriented_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_llm_delegation_1st',
        display_name='TG_llm_delegation_1st',
        app_sequence=['TG_llm_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_llm_delegation_2nd',
        display_name='TG_llm_delegation_2nd',
        app_sequence=['TG_llm_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_rule_based_delegation_1st',
        display_name='TG_rule_based_delegation_1st',
        app_sequence=['TG_rule_based_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_rule_based_delegation_2nd',
        display_name='TG_rule_based_delegation_2nd',
        app_sequence=['TG_rule_based_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_supervised_learning_delegation_1st',
        display_name='TG_supervised_learning_delegation_1st',
        app_sequence=['TG_supervised_learning_delegation_1st'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='TG_supervised_learning_delegation_2nd',
        display_name='TG_supervised_learning_delegation_2nd',
        app_sequence=['TG_supervised_learning_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=False,
    ),
    dict(
        name='prisoners_dilemma_automatic',
        display_name='prisoners_dilemma_automatic',
        app_sequence=['PD_goal_oriented_delegation_2nd'],
        num_demo_participants=10,
        use_browser_bots=True,
    ),
    dict(
        name='prisoners_dilemma_100',
        display_name='prisoners_dilemma_100',
        app_sequence=['PD_goal_oriented_delegation_2nd'],
        num_demo_participants=100,
        use_browser_bots=True,
    ),
]

ROOMS = [
    dict(
        name='PD_goal_oriented_delegation_2nd',
        display_name='PD_goal_oriented_delegation_2nd',
    ),
]

# if you set a property in SESSION_CONFIG_DEFAULTS, it will be inherited by all configs
# in SESSION_CONFIGS, except those that explicitly override it.
# the session config can be accessed from methods in your apps as self.session.config,
# e.g. self.session.config['participation_fee']

# if 10 points = 0.1 dollars then 1 point = 0.01 dollars
SESSION_CONFIG_DEFAULTS = dict(
    real_world_currency_per_point=0.01, participation_fee=6, doc=""
)

PARTICIPANT_FIELDS = []
SESSION_FIELDS = []

# ISO-639 code
# for example: de, fr, ja, ko, zh-hans
LANGUAGE_CODE = 'en'

# e.g. EUR, GBP, CNY, JPY
REAL_WORLD_CURRENCY_CODE = ''
USE_POINTS = False

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ """



SECRET_KEY = '9871076378040'
data_path='players_data/'

# Mistral (PD_llm_delegation_2nd): set MISTRAL_API_KEY in env or below; agent ID from your Mistral dashboard
MISTRAL_API_KEY = environ.get('MISTRAL_API_KEY', 'GRv8D2nDrIUaElftIpAPe2VcYqNfXR12')
MISTRAL_AGENT_ID = environ.get('MISTRAL_AGENT_ID', 'ag_019d000046b476f9b7937a71687e28a3')

# -----------------------------------------------------------------------------
# PostgreSQL connection resilience (reduce "SSL error: unexpected eof" on Clever Cloud)
# When DATABASE_URL is set we configure the DB with:
# - CONN_MAX_AGE: reuse connections up to 5 min then recycle (avoids server idle timeout).
# - CONN_HEALTH_CHECKS: ping before reuse so dropped connections are replaced (Django 4.1+).
# -----------------------------------------------------------------------------
if environ.get('DATABASE_URL'):
    try:
        import dj_database_url
        _db = dj_database_url.config(conn_max_age=300)
        if _db:
            _db['CONN_HEALTH_CHECKS'] = True
            DATABASES = {'default': _db}
    except ImportError:
        pass
else:
    try:
        _db = DATABASES.get('default', {})
        if _db and 'postgresql' in _db.get('ENGINE', ''):
            _db['CONN_MAX_AGE'] = 300
            _db['CONN_HEALTH_CHECKS'] = True
    except NameError:
        pass

# -----------------------------------------------------------------------------
# Default (wide) export: allow sessions where a round has 0 or mismatched players
# (e.g. dynamic grouping / players_per_group=None). Fill with empty cells instead of crashing.
# -----------------------------------------------------------------------------
def _patch_wide_export():
    import otree.export as _exp
    from collections import defaultdict
    from otree.common import get_models_module
    from otree.export import get_fields_for_csv, tweak_player_values_dict

    _orig = _exp.get_rows_for_wide_csv_app

    def _patched_get_rows_for_wide_csv_app(app_name, max_round_number, sessions):
        models_module = get_models_module(app_name)
        Player = models_module.Player
        Group = models_module.Group
        Subsession = models_module.Subsession
        pfields = get_fields_for_csv(Player)
        gfields = get_fields_for_csv(Group)
        sfields = get_fields_for_csv(Subsession)

        all_groups = Group.values_dicts()
        groups_by_round = defaultdict(dict)
        for g in all_groups:
            groups_by_round[g['round_number']][g['id']] = g

        session_ids = [s.id for s in sessions]
        all_subsessions = Subsession.values_dicts()
        subsessions_by_session_round = {}
        for s in all_subsessions:
            subsessions_by_session_round[(s['session_id'], s['round_number'])] = s

        all_players = Player.values_dicts(order_by='id')
        players_by_subsession = defaultdict(list)
        for p in all_players:
            players_by_subsession[p['subsession_id']].append(p)

        all_app_rows = []
        for round_number in range(1, max_round_number + 1):
            rows = []
            group_cache = groups_by_round.get(round_number, {})

            header_row = []
            for model_name, fields in [
                ('player', pfields),
                ('group', gfields),
                ('subsession', sfields),
            ]:
                for fname in fields:
                    header_row.append(f'{app_name}.{round_number}.{model_name}.{fname}')
            rows.append(header_row)
            empty_row = ['' for _ in range(len(header_row))]

            for session in sessions:
                subsession = subsessions_by_session_round.get((session.id, round_number))
                if not subsession:
                    subsession_rows = [empty_row for _ in range(session.num_participants)]
                else:
                    players = players_by_subsession.get(subsession['id'], [])

                    if len(players) != session.num_participants:
                        # Mismatch (e.g. 0 players): fill with empty rows so export completes
                        subsession_rows = [empty_row for _ in range(session.num_participants)]
                    else:
                        subsession_rows = []
                        for player in players:
                            group = group_cache.get(player['group_id'], {})
                            tweak_player_values_dict(player)
                            row = [player.get(fname, '') for fname in pfields]
                            row += [group.get(fname, '') for fname in gfields]
                            row += [subsession.get(fname, '') for fname in sfields]
                            subsession_rows.append(row)
                rows.extend(subsession_rows)
            all_app_rows.append(rows)

        if not all_app_rows:
            return []

        num_rows = len(all_app_rows[0])
        transposed = [[] for _ in range(num_rows)]
        for round_rows in all_app_rows:
            for i in range(len(round_rows)):
                if i == 0:
                    transposed[0].extend(round_rows[0])
                else:
                    transposed[i].extend(round_rows[i])
        return transposed

    _exp.get_rows_for_wide_csv_app = _patched_get_rows_for_wide_csv_app


_patch_wide_export()