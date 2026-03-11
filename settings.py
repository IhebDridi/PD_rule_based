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
REAL_WORLD_CURRENCY_CODE = 'USD'
USE_POINTS = True

ADMIN_USERNAME = 'admin'
# for security, best to set admin password in an environment variable
ADMIN_PASSWORD = environ.get('OTREE_ADMIN_PASSWORD')

DEMO_PAGE_INTRO_HTML = """ """



SECRET_KEY = '9871076378040'
data_path='players_data/'

