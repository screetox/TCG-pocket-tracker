import streamlit as st
import streamlit_authenticator as stauth
import supabase as sb
import pandas as pd

CURRENT_SERIES = 'Serie C'
CURRENT_BOOSTER = 'C1'


# ----------------------------------------------------------------------------------
# TITLE AND FAVICON

st.set_page_config(
    page_title='TCGP Tracker',
    page_icon='🎴'
)


# ----------------------------------------------------------------------------------
# CUSTOM CSS

def load_css(file_name):
    with open(file_name) as f:
        st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)

load_css('style.css')


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
# HELPER FUNCTIONS

# Map 0.0 (red) to 1.0 (green)
def color_percentage(val):
    if pd.isna(val):
        return ''

    v = max(0.0, min(1.0, float(val)))

    a = 0.1
    if v == 0 or v == 1:
        a = 0.2

    ratio = (v - 0.5) / 0.5
    r = int(234 + (34 - 234) * ratio)
    g = int(179 + (197 - 179) * ratio)
    b = int(8 + (94 - 8) * ratio)
    if v < 0.5:
        ratio = v / 0.5
        r = int(239 + (234 - 239) * ratio)
        g = int(68 + (179 - 68) * ratio)
        b = int(68 + (8 - 68) * ratio)

    return f'background-color: rgba({r}, {g}, {b}, {a});'

# Render statistics table
def render_stats_dataframe(
    df,
    column_order,
    row_height=35,
    header_height=38
):
    total_height = (len(df) * row_height) + header_height

    styled_df = df.style.map(
        color_percentage,
        subset=['percentage_all', 'percentage_diamond']
    )

    return st.dataframe(
        styled_df,
        column_order=column_order,
        column_config={
            'booster_id': st.column_config.TextColumn('ID'),
            'booster': st.column_config.TextColumn(
                'Booster',
                pinned=True,
                width=190
            ),
            'booster_display': st.column_config.TextColumn(
                'Booster',
                pinned=True,
                width=190
            ),
            'series': st.column_config.TextColumn('Serie'),
            'percentage_all': st.column_config.ProgressColumn(
                '% (Gesamt)',
                format='percent',
                min_value=0,
                max_value=1,
                step=0.001,
                color='rgb(250, 250, 250)',
                width=100
            ),
            'total_cards_all': st.column_config.NumberColumn('Gesamt'),
            'missing_all': st.column_config.NumberColumn('Fehlend'),
            'percentage_diamond': st.column_config.ProgressColumn(
                '% (Gezählt)',
                format='percent',
                min_value=0,
                max_value=1,
                step=0.001,
                color='rgb(250, 250, 250)',
                width=100
            ),
            'total_cards_diamond': st.column_config.NumberColumn('Gezählt'),
            'missing_diamond': st.column_config.NumberColumn('Fehlend'),
            'diamond_1': st.column_config.NumberColumn('♢'),
            'diamond_2': st.column_config.NumberColumn('♢♢'),
            'diamond_3': st.column_config.NumberColumn('♢♢♢'),
            'diamond_4': st.column_config.NumberColumn('♢♢♢♢'),
            'star_1': st.column_config.NumberColumn('☆'),
            'star_2': st.column_config.NumberColumn('☆☆'),
            'star_3': st.column_config.NumberColumn('☆☆☆'),
            'shiny_1': st.column_config.NumberColumn('✸'),
            'shiny_2': st.column_config.NumberColumn('✸✸'),
            'crown': st.column_config.NumberColumn('♛')
        },
        hide_index=True,
        placeholder='-',
        height=total_height,
        row_height=row_height
    )


# ----------------------------------------------------------------------------------
# MAIN APP

st.title(
    ':rainbow[Pokémon TCG Pocket Tracker]',
    icon='🎴',
    text_alignment='center'
)
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
    st.sidebar.error(f'Fehler: {e}')


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
        tab_tracker, tab_stats, tab_comparison, tab_admin = st.tabs(
            ['Tracker', 'Statistik', 'Vergleich', 'Admin'],
        )
    else:
        tab_tracker, tab_stats, tab_comparison = st.tabs(
            ['Tracker', 'Statistik', 'Vergleich']
        )

    # --- FEATURE 1: TRACK CARD COUNTS ---
    with tab_tracker:
        st.header('Karten Sammlung', icon='📝')

        col1, col2 = st.columns(2)

        # Filter for specific series
        with col1:
            series_data = supabase.table('series').select('*').execute().data or []
            series_list = [s['series_name'] for s in series_data]

            default_series_index = series_list.index(CURRENT_SERIES) \
                if CURRENT_SERIES in series_list else 0

            selected_series = st.selectbox(
                'Wähle eine Serie:',
                series_list,
                index=default_series_index
            )

        # Select specific booster
        with col2:
            booster_data = (
                supabase.table('booster')
                .select('*')
                .eq('series', selected_series)
                .execute()
                .data or []
            )
            booster_list = [p['booster_name'] for p in booster_data]
            booster_dict = {p['booster_name']: p['id'] for p in booster_data}

            default_booster_index = booster_list.index(CURRENT_BOOSTER) \
                if CURRENT_BOOSTER in booster_list else 0

            selected_booster = st.selectbox(
                'Wähle ein Booster:',
                booster_list,
                index=default_booster_index,
                format_func=lambda name: f'{name} ({booster_dict.get(name, '')})' \
                    if name in booster_dict else name
            )

        st.html('''
            <hr style="height: 1px; border-radius: 1px; border: 0;
                background: #FFF2; margin: 1rem 0;">
        ''')

        if 'editor_rev' not in st.session_state:
            st.session_state.editor_rev = 0

        if 'current_booster' not in st.session_state \
            or st.session_state.current_booster != selected_booster:
            st.session_state.current_booster = selected_booster
            st.session_state.editor_rev = 0

        # Get cards and user collection data
        cards_data = (
            supabase.table('cards')
            .select('*')
            .eq('booster_name', selected_booster)
            .execute()
            .data or []
        )

        collection_data = (
            supabase.table('collection')
            .select('group_id, quantity')
            .eq('user_id', user_id)
            .execute()
            .data or []
        )

        user_counts = {
            item['group_id']: item['quantity'] for item in collection_data
        }

        table_rows = []
        for card in cards_data:
            group_id = card.get('group_id')
            table_rows.append({
                'id': card.get('id'),
                'group': group_id,
                'name': card.get('name'),
                'booster': card.get('booster_name'),
                'notiz': card.get('note'),
                'seltenheit': card.get('rarity'),
                'quantity': user_counts.get(group_id, '0')
            })

        df_rows = pd.DataFrame(table_rows)
        if not df_rows.empty:
            df_rows = df_rows.set_index('id')

        editor_key = f'editor_{selected_booster}_{st.session_state.editor_rev}'

        button_container = st.container()
        table_container = st.container()

        # Display data, make quantity field editable
        with table_container:
            row_height = 35
            header_height = 38
            total_height = (len(df_rows) * row_height) + header_height

            edited_df = st.data_editor(
                df_rows,
                column_order=['name', 'notiz', 'seltenheit', 'quantity'],
                disabled=['id', 'group', 'name', 'booster', 'notiz', 'seltenheit'],
                column_config={
                    'id': st.column_config.TextColumn('ID'),
                    'group': st.column_config.NumberColumn('ID (Gruppe)'),
                    'name': st.column_config.TextColumn('Name'),
                    'notiz': st.column_config.TextColumn('Notiz'),
                    'seltenheit': st.column_config.TextColumn('Seltenheit'),
                    'quantity': st.column_config.TextColumn('#', max_chars=2),
                    'booster': st.column_config.TextColumn('Booster')
                },
                placeholder='-',
                height=total_height,
                row_height=row_height,
                on_change='ignore',
                key=editor_key
            )

        # Commit data to DB
        with button_container:
            if st.button('Änderungen speichern', icon='💾', shortcut='Ctrl+S'):
                group_updates = {}
                has_raw_edits = False

                for card_id, row in edited_df.iterrows():
                    old_val = str(df_rows.loc[card_id, 'quantity']).strip()
                    val = str(row['quantity']).strip()

                    if val != old_val:
                        has_raw_edits = True

                    if val.isdigit():
                        num = int(val)
                        if num >= 3:
                            final_val = '3+'
                        elif num in [1, 2]:
                            final_val = str(num)
                        else:
                            final_val = '0'
                    elif val == '3+':
                        final_val = '3+'
                    else:
                        final_val = '0'

                    if final_val != old_val:
                        group_id = row['group']
                        group_updates[group_id] = final_val

                upsert_payload = []
                delete_group_ids = []

                for group_id, final_val in group_updates.items():
                    if final_val != '0':
                        upsert_payload.append({
                            'user_id': user_id,
                            'group_id': group_id,
                            'quantity': final_val
                        })
                    else:
                        delete_group_ids.append(group_id)

                try:
                    if upsert_payload:
                        supabase.table('collection').upsert(
                            upsert_payload,
                            on_conflict='user_id,group_id'
                        ).execute()

                    if delete_group_ids:
                        supabase.table('collection') \
                            .delete() \
                            .eq('user_id', user_id) \
                            .in_('group_id', delete_group_ids) \
                            .execute()

                    total_updates = len(group_updates)
                    if total_updates == 0:
                        st.toast(
                            'Keine Änderungen zum Speichern vorhanden.',
                            icon='⚠️',
                            duration='long'
                        )
                        if has_raw_edits:
                            st.session_state.editor_rev += 1
                            st.rerun()
                    else:
                        st.toast(
                            f'''{total_updates} Karte{'n' \
                                if total_updates > 1 else ''} aktualisiert!''',
                            icon='✔️',
                            duration='long'
                        )

                        st.session_state.editor_rev += 1
                        st.rerun()

                except Exception as e:
                    st.toast(
                        f'Fehler beim Speichern: {e}',
                        icon='❌',
                        duration='long'
                    )

    # --- FEATURE 2: SHOW STATISTICS ---
    with tab_stats:
        st.header('Karten Statstik', icon='📊')

        tab_general_booster, tab_sub_booster = st.tabs(
            ['Gesamte Booster', 'Einzelne Booster']
        )

        with tab_general_booster:
            st.info('Diese Statistik enthält *alle* Karten \
                (auch aus Missionen und gegen Echtgeld).')

            booster_stats_response = (
                supabase.rpc('get_booster_stats', { 'p_user_id': user_id })
                .execute()
            )
            stats_df = pd.DataFrame(booster_stats_response.data)

            rarity_cols = [
                'diamond_1', 'diamond_2', 'diamond_3', 'diamond_4',
                'star_1', 'star_2', 'star_3', 'shiny_1', 'shiny_2', 'crown'
            ]
            stats_df[rarity_cols] = stats_df[rarity_cols].replace(0, None)

            render_stats_dataframe(
                stats_df,
                column_order=[
                    'booster', 'percentage_all', 'total_cards_all',
                    'missing_all', 'percentage_diamond',
                    'total_cards_diamond', 'missing_diamond'
                ]
            )

            render_stats_dataframe(
                stats_df,
                column_order=[
                    'booster', 'diamond_1', 'diamond_2',
                    'diamond_3', 'diamond_4', 'star_1', 'star_2',
                    'star_3', 'shiny_1', 'shiny_2', 'crown'
                ]
            )

        with tab_sub_booster:
            st.info('Diese Statistik enthält *keine* Karten \
                aus Missionen und gegen Echtgeld.')

            sub_booster_stats_ratio_response = (
                supabase.rpc('get_sub_booster_stats', { 'p_user_id': user_id })
                .execute()
            )
            sub_stats_df = pd.DataFrame(sub_booster_stats_ratio_response.data)

            rarity_cols = [
                'diamond_1', 'diamond_2', 'diamond_3', 'diamond_4',
                'star_1', 'star_2', 'star_3', 'shiny_1', 'shiny_2', 'crown'
            ]
            sub_stats_df[rarity_cols] = sub_stats_df[rarity_cols].replace(0, None)

            render_stats_dataframe(
                sub_stats_df,
                column_order=[
                    'booster_display', 'percentage_all', 'total_cards_all',
                    'missing_all', 'percentage_diamond','total_cards_diamond',
                    'missing_diamond'
                ]
            )

            render_stats_dataframe(
                sub_stats_df,
                column_order=[
                    'booster_display', 'diamond_1', 'diamond_2',
                    'diamond_3', 'diamond_4', 'star_1', 'star_2',
                    'star_3', 'shiny_1', 'shiny_2', 'crown'
                ]
            )

    # --- FEATURE 3: COMPARE TO OTHER USERS ---
    with tab_comparison:
        st.header('Karten Vergleich', icon='👥')
        st.warning('''
            Dieser Bereich ist noch nicht fertiggestellt.
            Schau später nochmal vorbei.
        ''')

    # --- ADMIN ONLY CONTENT ---
    if user_role == 'admin':
        with tab_admin:
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
