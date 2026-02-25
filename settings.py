from os import environ

SESSION_CONFIGS = [
    dict(
        name='prisoners_dilemma',
        display_name="Rule Based Delegation First",
        app_sequence=['prisoners_dilemma'],  # This links to your app folder
        num_demo_participants=10,  # Adjust as needed
        use_browser_bots=False,
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

