import streamlit as st
import streamlit_authenticator as stauth
import supabase as sb


# ----------------------------------------------------------------------------------
# TITLE AND FAVICON

st.set_page_config(
    page_title='TCGP Tracker',
    page_icon='🎴',
)


# ----------------------------------------------------------------------------------
# CUSTOM CSS

st.html('''<style>
    [data-testid='InputInstructions'],
    [data-testid='stInputInstructions'] {
        display: none;
    }

    header {
        background: transparent !important;
    }

    main > div {
        padding-top: 0 !important;
        padding-bottom: 5rem !important;
    }

    h1 {
        padding-top: 0 !important;
    }
</style>''')


# ----------------------------------------------------------------------------------
# DATABASE CONNECTION

@st.cache_resource
def init_supabase() -> sb.Client:
    url = st.secrets['supabase_url']
    key = st.secrets['supabase_key']
    return sb.create_client(url, key)

supabase = init_supabase()
users_data = supabase.table('users').select('*').execute().data or []
user_list = [u['username'] for u in users_data]


# ----------------------------------------------------------------------------------
# INITIALIZE AUTHENTICATOR

credentials = {'usernames': {}}
for user in users_data:
    credentials['usernames'][user['username']] = {
        'name': user['username'],
        'password': user['password']
    }

authenticator = stauth.Authenticate(
    credentials=credentials,
    cookie_name='tcgp_session_id',
    cookie_key=st.secrets['cookie_key'],
    cookie_expiry_days=30
)


# ----------------------------------------------------------------------------------
# MAIN APP

st.title(':rainbow[Pokémon TCG Pocket Tracker]', icon='🎴')
st.sidebar.title('Einstellungen')


# ----------------------------------------------------------------------------------
# LOGIN FORM

try:
    authenticator.login(
        key='login_form',
        location='sidebar',
        fields={
            'Form name': 'Einloggen',
            'Username': 'Benutzername',
            'Password': 'Passwort',
            'Login': 'Login',
            'Captcha': 'Captcha'
        }
    )
except Exception as e:
    st.sidebar.error(e)


# ----------------------------------------------------------------------------------
# LOGGED IN

if st.session_state.get('authentication_status'):
    user_name = st.session_state.get('name')
    current_user = next((u for u in users_data if u['username'] == user_name), {})
    user_id = current_user.get('id')
    user_role = current_user.get('role')

    # --- LOGOUT FORM ---
    st.sidebar.success(f'Hallo **{user_name}**!')
    if user_role == 'admin':
        st.sidebar.caption('🛠️ Admin-Modus aktiv')
    authenticator.logout('Logout', location='sidebar')

    # --- NAVIGATION ---
    if user_role == 'admin':
        tabs = st.tabs(['Tracker', 'Statistik', 'Vergleich', 'Admin'])
    else:
        tabs = st.tabs(['Tracker', 'Statistik', 'Vergleich'])

    # --- FEATURE 1: TRACK CARD COUNTS ---
    with tabs[0]:
        st.header('Karten Sammlung', icon='📝')
        st.warning('''
            Dieser Bereich ist noch nicht fertiggestellt.
            Schau später nochmal vorbei.
        ''')

    # --- FEATURE 2: SHOW STATISTICS ---
    with tabs[1]:
        st.header('Karten Statstik', icon='📊')
        st.warning('''
            Dieser Bereich ist noch nicht fertiggestellt.
            Schau später nochmal vorbei.
        ''')

    # --- FEATURE 3: COMPARE TO OTHER USERS ---
    with tabs[2]:
        st.header('Karten Vergleich', icon='👥')
        st.warning('''
            Dieser Bereich ist noch nicht fertiggestellt.
            Schau später nochmal vorbei.
        ''')

    # --- ADMIN ONLY CONTENT ---
    if user_role == 'admin':
        with tabs[3]:
            st.header('Admin Dashboard', icon='🛠️')
            st.warning('''
                Dieser Bereich ist noch nicht fertiggestellt.
                Schau später nochmal vorbei.
            ''')


# ----------------------------------------------------------------------------------
# LOGGED OUT

else:
    st.warning('''
        Für die Nutzung dieses Tools ist ein Login in der Seitenleiste notwendig.
    ''')

    if st.session_state.get('authentication_status') is False:
        st.sidebar.error('Benutzername oder Passwort falsch!')
