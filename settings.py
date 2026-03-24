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
        use_browser_bots=False,
    ),
    dict(
        name='prisoners_dilemma_100',
        display_name='prisoners_dilemma_100',
        app_sequence=['PD_goal_oriented_delegation_2nd'],
        num_demo_participants=100,
        use_browser_bots=False,
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
#MISTRAL_API_KEY = environ.get('MISTRAL_API_KEY', '')
#MISTRAL_AGENT_ID = environ.get('MISTRAL_AGENT_ID', '')

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
# SQLAlchemy pool resilience for cloud PostgreSQL (e.g. Clever Cloud):
# - pool_pre_ping=True: validates pooled connection before use.
# - pool_recycle: recycle before the provider idle/SSL timeout (Clever Cloud often < 5 min).
# Guards "SSL error: unexpected eof" on otree_taskqueuemessage and other SA pools.
#
# NOTE: Older code patched sqlalchemy.engine.create — that module does not exist in
# SQLAlchemy 1.4+/2.x, so the patch silently did nothing. Patch engine.create_engine
# and re-bind sqlalchemy.create_engine so all import styles see the wrapper.
# -----------------------------------------------------------------------------
try:
    import sqlalchemy
    import sqlalchemy.engine as _sa_engine

    _orig_sa_create_engine = _sa_engine.create_engine
    _pool_recycle = int(environ.get("SQLALCHEMY_POOL_RECYCLE_SECONDS", "120"))

    def _create_engine_with_pool_guards(*args, **kwargs):
        kwargs.setdefault("pool_pre_ping", True)
        kwargs.setdefault("pool_recycle", _pool_recycle)
        return _orig_sa_create_engine(*args, **kwargs)

    _sa_engine.create_engine = _create_engine_with_pool_guards
    sqlalchemy.create_engine = _create_engine_with_pool_guards
except Exception:
    # Keep startup robust if SQLAlchemy is missing or API differs.
    pass