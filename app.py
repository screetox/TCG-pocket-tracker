import streamlit as st
import streamlit_authenticator as stauth
import supabase as sb
import pandas as pd
import datetime as dt

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
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

load_css('style.css')


# ----------------------------------------------------------------------------------
# DATABASE CONNECTION

@st.cache_resource(show_spinner=False)
def init_supabase() -> sb.Client:
    url = st.secrets['supabase_url']
    key = st.secrets['supabase_key']
    return sb.create_client(url, key)

supabase = init_supabase()


# ----------------------------------------------------------------------------------
# GLOBAL CACHES

@st.cache_data(show_spinner=False)
def get_users_data():
    return (
        supabase.table('users')
        .select('*')
        .order('id')
        .execute().data or []
    )

@st.cache_data(show_spinner=False)
def get_series_data():
    return (
        supabase.table('series')
        .select('*')
        .order('series_name')
        .execute().data or []
    )

@st.cache_data(show_spinner=False)
def get_booster_data(series_name=None):
    query = supabase.table('booster').select('*').order('id')
    if series_name:
        query = query.eq('series', series_name)
    return query.execute().data or []

@st.cache_data(show_spinner=False)
def get_all_cards():
    all_data = []
    start = 0
    step = 1000

    while True:
        data = (
            supabase.table('cards')
            .select('*')
            .order('id')
            .range(start, start + step - 1)
            .execute().data or []
        )

        if not data:
            break

        all_data.extend(data)

        if len(data) < step:
            break

        start += step

    return all_data

@st.cache_data(show_spinner=False)
def get_cards_data(booster_name):
    return (
        supabase.table('cards')
        .select('*')
        .eq('booster_name', booster_name)
        .order('id')
        .execute().data or []
    )


# ----------------------------------------------------------------------------------
# USER CACHES

@st.cache_data(ttl=dt.timedelta(days=1), show_spinner=False)
def get_collection_data(user_id):
    return (
        supabase.table('collection')
        .select('group_id, quantity')
        .eq('user_id', user_id)
        .execute().data or []
    )

@st.cache_data(ttl=dt.timedelta(days=1), show_spinner=False)
def get_booster_stats_data(user_id):
    return (
        supabase.rpc('get_booster_stats', { 'p_user_id': user_id })
        .execute().data or []
    )

@st.cache_data(ttl=dt.timedelta(days=1), show_spinner=False)
def get_sub_booster_stats_data(user_id):
    return (
        supabase.rpc('get_sub_booster_stats', { 'p_user_id': user_id })
        .execute().data or []
    )

users_data = get_users_data()
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
    cookie_expiry_days=365,
    auto_hash=False
)


# ----------------------------------------------------------------------------------
# HELPER FUNCTIONS

def render_collection_editor(cards_data, view_key, user_id):
    if not cards_data:
        st.info('Keine Karten gefunden.')
        return

    rev_key = f'editor_rev_{view_key}'
    if rev_key not in st.session_state:
        st.session_state[rev_key] = 0

    collection_data = get_collection_data(user_id)
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
            'quantity': user_counts.get(group_id, None)
        })

    df_rows = pd.DataFrame(table_rows)
    if not df_rows.empty:
        df_rows = df_rows.set_index('id')

    editor_key = f'editor_{view_key}_{st.session_state[rev_key]}'

    with st.form(key=f'form_{editor_key}'):
        submit_edits = st.form_submit_button(
            'Änderungen speichern',
            icon='💾',
            shortcut='Ctrl+S',
            key=f'submit_form_{editor_key}'
        )

        row_height = 35
        header_height = 38
        total_height = (
            (len(df_rows) * row_height) + header_height
            if len(df_rows) < 900 else 'auto'
        )

        st.data_editor(
            df_rows,
            column_order=['name', 'booster', 'notiz', 'seltenheit', 'quantity'],
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

        if submit_edits:
            changes = st.session_state[editor_key].get('edited_rows', {})

            if not changes:
                st.toast(
                    'Keine Änderungen zum Speichern vorhanden.',
                    icon='⚠️',
                    duration='long'
                )
                st.rerun()

            upsert_payload = []
            delete_group_ids = []
            actual_updates = 0

            for row_idx, edit in changes.items():
                if 'quantity' in edit:
                    new_raw = edit['quantity']
                    val = str(new_raw).strip() if pd.notna(new_raw) else ''

                    card_id = df_rows.index[row_idx]
                    group_id = int(df_rows.loc[card_id, 'group'])

                    old_raw = df_rows.loc[card_id, 'quantity']
                    old_val = str(old_raw).strip() if pd.notna(old_raw) else ''

                    if val.isdigit():
                        num = int(val)
                        if num >= 3:
                            final_val = '3+'
                        elif num in [1, 2]:
                            final_val = str(num)
                        else:
                            final_val = ''
                    elif val == '3+':
                        final_val = '3+'
                    else:
                        final_val = ''

                    if final_val != old_val:
                        actual_updates += 1
                        if final_val != '':
                            upsert_payload.append({
                                'user_id': user_id,
                                'group_id': group_id,
                                'quantity': final_val
                            })
                        else:
                            delete_group_ids.append(group_id)

            if actual_updates == 0:
                st.toast(
                    'Keine Änderungen zum Speichern vorhanden.',
                    icon='⚠️',
                    duration='long'
                )
                st.session_state[rev_key] += 1
                st.rerun()

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

                get_collection_data.clear()
                get_booster_stats_data.clear()
                get_sub_booster_stats_data.clear()

                st.toast(
                    f'{actual_updates} Karte(n) aktualisiert!',
                    icon='✔️',
                    duration='long'
                )

                st.session_state[rev_key] += 1
                st.rerun()

            except Exception as e:
                st.toast(
                    f'Fehler beim Speichern: {e}',
                    icon='❌',
                    duration='long'
                )

def search_cards_data(query):
    matched_cards = []
    all_cards = get_all_cards()

    for card in all_cards:
        if query.lower() in str(card.get('name', '')).lower():
            matched_cards.append(card)

    matched_cards.sort(key=lambda x: x.get('id', ''))
    return matched_cards

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

def render_stats_dataframe(df, column_order, row_height=35, header_height=38):
    total_height = (
        (len(df) * row_height) + header_height
        if len(df) < 900 else 'auto'
    )

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

def get_base_rarity(rarity_str):
    if not rarity_str:
        return None
    return rarity_str.replace(' parallel', '')

@st.dialog('Passwort ändern', icon='🔑')
def change_password(user_name):
    try:
        auth_username = user_name.lower()

        if authenticator.reset_password(
            username=auth_username,
            fields={
                'Form name': 'Passwort ändern',
                'Current password': 'Aktuelles Passwort',
                'New password': 'Neues Passwort',
                'Repeat password': 'Neues Passwort wiederholen',
                'Reset': 'Passwort ändern'
            }
        ):
            new_password_hash = credentials['usernames'][auth_username]['password']

            supabase.table('users').update({
                'password': new_password_hash
            }).eq('username', user_name).execute()

            get_users_data.clear()

            st.success('Passwort erfolgreich geändert.')

    except Exception as e:
        st.error(f'Fehler: {e}')

@st.dialog('Booster erstellen', icon='🗃️')
def booster_creation_dialog(missing_booster):
    series_data = get_series_data()
    valid_series = [row['series_name'] for row in series_data]

    if not valid_series:
        st.error('Keine Serie gefunden, um einen Booster hinzuzufügen.')
        return

    booster_to_submit = {}

    for booster in missing_booster:
        st.subheader(booster)

        create_it = st.checkbox(
            f'*{booster}* erstellen',
            value=True,
            key=f'checkbox_{booster}'
        )

        booster_creation_left, booster_creation_right = st.columns([1, 2])

        with booster_creation_left:
            booster_id = st.text_input(
                f'ID für *{booster}*',
                placeholder='A1',
                key=f'id_input_{booster}',
                disabled=not create_it
            )

        with booster_creation_right:
            selected_series = st.selectbox(
                f'Serie für *{booster}*',
                options=valid_series,
                index=None,
                placeholder='Serie auswählen...',
                key=f'series_selection_{booster}',
                disabled=not create_it
            )

        if create_it:
            booster_to_submit[booster] = {
                'id': booster_id,
                'booster_name': booster,
                'series': selected_series
            }

        st.divider()

    if st.button('Booster erstellen', icon='💾', key='create_booster_button'):
        records_to_insert = list(booster_to_submit.values())
        if not records_to_insert:
            st.warning('Keine Booster zum Erstellen ausgewählt.')
            return

        try:
            b_resp = supabase.table('booster').upsert(records_to_insert).execute()
            if b_resp.data:
                st.toast(
                    f'{len(b_resp.data)} Booster erfolgreich erstellt!',
                    icon='✔️',
                    duration='long'
                )

                get_booster_data.clear()
                get_booster_stats_data.clear()
                get_sub_booster_stats_data.clear()
                st.rerun()

        except Exception as e:
            st.toast(f'Fehler beim Speichern: {e}', icon='❌', duration='long')


# ----------------------------------------------------------------------------------
# MAIN APP

st.title(':rainbow[Pokémon TCG Pocket Tracker]', icon='🎴', text_alignment='center')
st.sidebar.title('Einstellungen')


# ----------------------------------------------------------------------------------
# LOGIN FORM

try:
    authenticator.login(
        key='login_form',
        location='sidebar',
        fields={
            'Form name': 'Einloggen', 'Username': 'Benutzername',
            'Password': 'Passwort', 'Login': 'Login', 'Captcha': 'Captcha'
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
    authenticator.logout('Logout', location='sidebar', use_container_width=True)
    if st.sidebar.button(
        'Passwort ändern',
        width='stretch',
        key='change_password_button'
    ):
        change_password(user_name)

    # --- NAVIGATION ---
    if user_role == 'admin':
        tab_collection, tab_stats, tab_comparison, tab_admin = st.tabs(
            ['Sammlung', 'Statistik', 'Vergleich', 'Admin'],
        )
    else:
        tab_collection, tab_stats, tab_comparison = st.tabs(
            ['Sammlung', 'Statistik', 'Vergleich']
        )

    # --- FEATURE 1: TRACK CARD COUNTS ---
    with tab_collection:
        st.header('Karten Sammlung', icon='📝')

        collection_tab_booster, collection_tab_search = \
            st.tabs(['Booster', 'Suche'])

        with collection_tab_booster:
            collection_booster_left, collection_booster_right = st.columns(2)

            with collection_booster_left:
                series_data = get_series_data()
                series_list = [s['series_name'] for s in series_data]

                default_series_index = series_list.index(CURRENT_SERIES) \
                    if CURRENT_SERIES in series_list else 0

                selected_series = st.selectbox(
                    'Wähle eine Serie:',
                    series_list,
                    index=default_series_index,
                    key='collection_series_select'
                )

            with collection_booster_right:
                booster_data = get_booster_data(selected_series)
                booster_list = [p['booster_name'] for p in booster_data]
                booster_dict = {p['booster_name']: p['id'] for p in booster_data}

                default_booster_index = booster_list.index(CURRENT_BOOSTER) \
                    if CURRENT_BOOSTER in booster_list else 0

                selected_booster = st.selectbox(
                    'Wähle ein Booster:',
                    booster_list,
                    index=default_booster_index,
                    key='collection_booster_select',
                    format_func=lambda name: (
                        f'{name} ({booster_dict.get(name, "")})'
                        if name in booster_dict else name
                    )
                )

            cards_data_booster = get_cards_data(selected_booster)
            render_collection_editor(
                cards_data_booster,
                f'booster_{selected_booster}',
                user_id
            )

        with collection_tab_search:
            search_query = st.text_input(
                'Suche nach einer Karte:',
                placeholder='Kartenname eingeben...',
                label_visibility='collapsed',
                live=True,
                icon='🔍',
                key='search_input'
            )

            if search_query.strip() and len(search_query.strip()) >= 3:
                cards_data_search = search_cards_data(search_query.strip())

                render_collection_editor(
                    cards_data_search,
                    f'search_{search_query.strip()}',
                    user_id
                )
            else:
                st.caption('Gib mindestens 3 Zeichen (ohne Leerzeichen) ein, \
                    um die Suche zu starten.')

    # --- FEATURE 2: SHOW STATISTICS ---
    with tab_stats:
        st.header('Karten Statistik', icon='📊')

        (
            stats_tab_general_booster,
            stats_tab_sub_booster,
            stats_tab_missing_cards
        ) = st.tabs(
            ['Gesamte Booster', 'Einzelne Booster', 'Fehlende Karten']
        )

        rarity_cols = [
            'diamond_1', 'diamond_2', 'diamond_3', 'diamond_4',
            'star_1', 'star_2', 'star_3', 'shiny_1', 'shiny_2', 'crown'
        ]

        with stats_tab_general_booster:
            st.caption('Diese Statistik enthält *alle* Karten \
                (auch aus Missionen und gegen Echtgeld).')

            stats_data = get_booster_stats_data(user_id)
            stats_df = pd.DataFrame(stats_data)
            if not stats_df.empty:
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
                column_order=['booster'] + rarity_cols
            )

        with stats_tab_sub_booster:
            st.caption('Diese Statistik enthält *keine* Karten \
                aus Missionen und gegen Echtgeld.')

            sub_stats_data = get_sub_booster_stats_data(user_id)
            sub_stats_df = pd.DataFrame(sub_stats_data)
            if not sub_stats_df.empty:
                sub_stats_df[rarity_cols] = sub_stats_df[rarity_cols] \
                    .replace(0, None)

            render_stats_dataframe(
                sub_stats_df,
                column_order=[
                    'booster_display', 'percentage_all', 'total_cards_all',
                    'missing_all', 'percentage_diamond', 'total_cards_diamond',
                    'missing_diamond'
                ]
            )

            render_stats_dataframe(
                sub_stats_df,
                column_order=['booster_display'] + rarity_cols
            )

        with stats_tab_missing_cards:
            with st.expander(
                'Filter & Einstellungen',
                icon='⚙️',
                expanded=True,
                key='missing_filter_expander'
            ):
                filter_mode = st.radio(
                    'Filtern nach:',
                    ['Booster', 'Seltenheit'],
                    horizontal=True,
                    key='missing_filter_mode'
                )

                if filter_mode == 'Booster':
                    missing_left, missing_right = st.columns(2)
                    with missing_left:
                        missing_series_data = get_series_data()
                        missing_series_list = [
                            s['series_name'] for s in missing_series_data
                        ]
                        missing_default_series_index = \
                            missing_series_list.index(CURRENT_SERIES) \
                            if CURRENT_SERIES in series_list else 0

                        missing_selected_series = st.selectbox(
                            'Wähle eine Serie:',
                            missing_series_list,
                            index=missing_default_series_index,
                            key='missing_series_select'
                        )

                    with missing_right:
                        missing_booster_data = get_booster_data(
                            missing_selected_series
                        )
                        missing_booster_list = [
                            b['booster_name'] for b in missing_booster_data
                        ]
                        missing_booster_dict = {
                            b['booster_name']: b['id'] for b in missing_booster_data
                        }
                        missing_default_booster_index = \
                            missing_booster_list.index(CURRENT_BOOSTER) \
                            if CURRENT_BOOSTER in missing_booster_list else 0

                        missing_selected_booster = st.selectbox(
                            'Wähle ein Booster:',
                            missing_booster_list,
                            index=missing_default_booster_index,
                            key='missing_booster_select',
                            format_func=lambda name: (
                                f'{name} ({missing_booster_dict.get(name, "")})'
                                if name in missing_booster_dict else name
                            )
                        )

                    missing_cards_data = get_cards_data(missing_selected_booster)

                elif filter_mode == 'Seltenheit':
                    all_cards = get_all_cards()
                    available_rarities = sorted(list({
                        get_base_rarity(c.get('rarity'))
                        for c in all_cards if c.get('rarity')
                    }))

                    MANUAL_ORDER = [
                        '♢', '♢♢', '♢♢♢', '♢♢♢♢',
                        '☆', '☆☆', '☆☆☆',
                        '✸', '✸✸', '♛'
                    ]
                    available_rarities.sort(
                        key=(
                            lambda x: MANUAL_ORDER.index(x)
                            if x in MANUAL_ORDER else 999
                        )
                    )

                    selected_rarity = st.selectbox(
                        'Wähle eine Seltenheit:',
                        available_rarities,
                        index=0,
                        key='missing_rarity_select'
                    )

                    missing_cards_data = [
                        c for c in all_cards
                        if c.get('rarity')
                        and get_base_rarity(c.get('rarity')) == selected_rarity
                    ]

            if missing_cards_data:
                my_collection = get_collection_data(user_id)

                my_counts = {
                    item['group_id']: item.get('quantity')
                    for item in my_collection
                }

                other_users = [u for u in users_data if u['id'] != user_id]
                other_counts = {
                    u['username']: {
                        item['group_id']: str(item.get('quantity'))
                        for item in get_collection_data(u['id'])
                    }
                    for u in other_users
                }

                missing_rows = []
                for card in missing_cards_data:
                    group_id = card.get('group_id')
                    i_have = group_id in my_counts

                    if i_have:
                        continue

                    available_from = [
                        uname for uname, counts in other_counts.items()
                        if counts.get(group_id) in ['2', '3+']
                    ]
                    available_from_str = ', '.join(available_from) \
                        if available_from else None

                    missing_rows.append({
                        'id': card.get('id'),
                        'name': card.get('name'),
                        'booster': card.get('booster_name'),
                        'rarity': card.get('rarity'),
                        'available_from': available_from_str
                    })

                if not missing_rows:
                    st.info(
                        'Keine Karten gefunden, die den Kriterien entsprechen.'
                    )
                else:
                    df_comp = pd.DataFrame(missing_rows)
                    df_comp = df_comp.set_index('id')

                    row_height = 35
                    header_height = 38
                    total_height = (
                        (len(df_comp) * row_height) + header_height
                        if len(df_comp) < 900 else 'auto'
                    )

                    st.dataframe(
                        df_comp,
                        column_order=[
                            'id', 'name', 'booster', 'rarity', 'available_from'
                        ],
                        column_config={
                            'id': st.column_config.TextColumn('ID'),
                            'name': st.column_config.TextColumn('Name'),
                            'booster': st.column_config.TextColumn('Booster'),
                            'rarity': st.column_config.TextColumn(
                                'Seltenheit'
                            ),
                            'available_from': st.column_config.TextColumn(
                                'Hat Karte mehrfach'
                            )
                        },
                        placeholder='-',
                        height=total_height,
                        row_height=row_height
                    )

    # --- FEATURE 3: COMPARE TO OTHER USERS ---
    with tab_comparison:
        st.header('Karten Vergleich', icon='👥')

        with st.expander(
            'Filter & Einstellungen',
            icon='⚙️',
            expanded=True,
            key='comp_filter_expander'
        ):
            compare_user_left, compare_user_right = st.columns([2, 1])

            with compare_user_left:
                compare_user = st.selectbox(
                    'Sammlung vergleichen mit:',
                    [u for u in user_list if u != user_name],
                    key='comp_user_select'
                )

            with compare_user_right:
                filter_mode = st.radio(
                    'Filtern nach:',
                    ['Booster', 'Seltenheit'],
                    horizontal=True,
                    key='comp_filter_mode'
                )

            show_all = st.checkbox(
                'Karten anzeigen, die beide besitzen',
                key='comp_show_all_checkbox'
            )

            if compare_user:
                if filter_mode == 'Booster':
                    booster_comp_left, booster_comp_right = st.columns(2)
                    with booster_comp_left:
                        comp_series_data = get_series_data()
                        comp_series_list = [
                            s['series_name'] for s in comp_series_data
                        ]
                        comp_default_series_index = \
                            comp_series_list.index(CURRENT_SERIES) \
                            if CURRENT_SERIES in series_list else 0

                        comp_selected_series = st.selectbox(
                            'Wähle eine Serie:',
                            comp_series_list,
                            index=comp_default_series_index,
                            key='comp_series_select'
                        )

                    with booster_comp_right:
                        comp_booster_data = get_booster_data(comp_selected_series)
                        comp_booster_list = [
                            b['booster_name'] for b in comp_booster_data
                        ]
                        comp_booster_dict = {
                            b['booster_name']: b['id'] for b in comp_booster_data
                        }
                        comp_default_booster_index = \
                            comp_booster_list.index(CURRENT_BOOSTER) \
                            if CURRENT_BOOSTER in comp_booster_list else 0

                        comp_selected_booster = st.selectbox(
                            'Wähle ein Booster:',
                            comp_booster_list,
                            index=comp_default_booster_index,
                            key='comp_booster_select',
                            format_func=lambda name: (
                                f'{name} ({comp_booster_dict.get(name, "")})'
                                if name in comp_booster_dict else name
                            )
                        )

                elif filter_mode == 'Seltenheit':
                    all_cards = get_all_cards()
                    available_rarities = sorted(list({
                        get_base_rarity(c.get('rarity'))
                        for c in all_cards if c.get('rarity')
                    }))

                    MANUAL_ORDER = [
                        '♢', '♢♢', '♢♢♢', '♢♢♢♢',
                        '☆', '☆☆', '☆☆☆',
                        '✸', '✸✸', '♛'
                    ]
                    available_rarities.sort(
                        key=(
                            lambda x: MANUAL_ORDER.index(x)
                            if x in MANUAL_ORDER else 999
                        )
                    )

                    selected_rarity = st.selectbox(
                        'Wähle eine Seltenheit:',
                        available_rarities,
                        index=0,
                        key='comp_rarity_select'
                    )

        if compare_user:
            compare_user_dict = next(
                (u for u in users_data if u['username'] == compare_user),
                None
            )

            if compare_user_dict:
                compare_user_id = compare_user_dict['id']
                comp_cards_data = []

                if filter_mode == 'Booster':
                    comp_cards_data = get_cards_data(comp_selected_booster)
                elif filter_mode == 'Seltenheit':
                    all_cards = get_all_cards()
                    comp_cards_data = [
                        c for c in all_cards
                        if c.get('rarity')
                        and get_base_rarity(c.get('rarity')) == selected_rarity
                    ]

                if comp_cards_data:
                    my_collection = get_collection_data(user_id)
                    their_collection = get_collection_data(compare_user_id)

                    my_counts = {
                        item['group_id']: item.get('quantity')
                        for item in my_collection
                    }
                    their_counts = {
                        item['group_id']: item.get('quantity')
                        for item in their_collection
                    }

                    comparison_rows = []
                    for card in comp_cards_data:
                        group_id = card.get('group_id')
                        i_have = group_id in my_counts
                        they_have = group_id in their_counts

                        if not show_all and i_have and they_have:
                            continue

                        if i_have and they_have:
                            status = '🟢 Beide'
                        elif i_have:
                            status = f'🔵 Nur {user_name}'
                        elif they_have:
                            status = f'🟡 Nur {compare_user}'
                        else:
                            status = '🔴 Keiner'

                        comparison_rows.append({
                            'id': card.get('id'),
                            'name': card.get('name'),
                            'booster': card.get('booster'),
                            'rarity': card.get('rarity'),
                            'my_status': my_counts.get(group_id),
                            'their_status': their_counts.get(group_id),
                            'status': status
                        })

                    if not comparison_rows:
                        st.info(
                            'Keine Karten gefunden, die den Kriterien entsprechen.'
                        )
                    else:
                        df_comp = pd.DataFrame(comparison_rows)
                        df_comp = df_comp.set_index('id')

                        row_height = 35
                        header_height = 38
                        total_height = (
                            (len(df_comp) * row_height) + header_height
                            if len(df_comp) < 900 else 'auto'
                        )

                        st.dataframe(
                            df_comp,
                            column_order=[
                                'id', 'name', 'rarity', 'my_status',
                                'their_status', 'status'
                            ],
                            column_config={
                                'id': st.column_config.TextColumn('ID'),
                                'name': st.column_config.TextColumn('Name'),
                                'status': st.column_config.TextColumn('Vergleich'),
                                'rarity': st.column_config.TextColumn(
                                    'Seltenheit'
                                ),
                                'my_status': st.column_config.TextColumn(
                                    f'{user_name}',
                                    max_chars=2
                                ),
                                'their_status': st.column_config.TextColumn(
                                    f'{compare_user}',
                                    max_chars=2
                                )
                            },
                            placeholder='-',
                            height=total_height,
                            row_height=row_height
                        )

    # --- ADMIN ONLY CONTENT ---
    if user_role == 'admin':
        with tab_admin:
            st.header('Admin Dashboard', icon='🛠️')

            st.subheader('System-Wartung')
            if st.button(
                'Gesamten Cache leeren',
                icon='♻️',
                key='delete_cache_button'
            ):
                try:
                    st.cache_data.clear()
                    st.toast(
                        'Der Cache wurde erfolgreich geleert. \
                            Alle Daten sind wieder live!',
                        icon='✔️',
                        duration='long'
                    )
                except Exception as e:
                    st.error(f'Fehler: {e}')

            st.divider()

            st.subheader('Neue Karten hochladen')
            uploaded_file = st.file_uploader(
                '**CSV Datei auswählen**',
                type=['csv', 'xlsx'],
                key='new_cards_upload'
            )

            if uploaded_file is not None:
                try:
                    if uploaded_file.name.endswith('.csv'):
                        file_df = pd.read_csv(uploaded_file)
                    elif uploaded_file.name.endswith('.xlsx'):
                        file_df = pd.read_excel(uploaded_file, engine='openpyxl')

                    file_df = file_df.where(pd.notnull(file_df), None)
                    file_df.columns = file_df.columns.str.strip()

                    required_cols = {
                        'id', 'name', 'booster_name', 'rarity', 'note', 'group_id'
                    }
                    missing_cols = required_cols - set(file_df.columns)

                    if missing_cols:
                        st.error(
                            f'''Fehlende Spalten: {', '.join(missing_cols)}'''
                        )

                        st.write('**Vorschau:**')
                        st.dataframe(
                            file_df,
                            width='content',
                            hide_index=True,
                            placeholder='-'
                        )

                    else:
                        file_df = file_df.set_index('id')

                        rarities = {
                            'C Pocket': '♢',
                            'U Pocket': '♢♢',
                            'R Pocket': '♢♢♢',
                            'RR Pocket': '♢♢♢♢',
                            'SA Pocket': '☆',
                            'SSASR Pocket': '☆☆',
                            'Immersion': '☆☆☆',
                            'S Pocket': '✸',
                            'SSR Pocket': '✸✸',
                            'UR Pocket': '♛',
                            'C Pocket parallel': '♢ parallel',
                            'U Pocket parallel': '♢♢ parallel',
                            'R Pocket parallel': '♢♢♢ parallel'
                        }
                        unmapped_rarities = (
                            set(file_df['rarity']) - set(rarities.keys())
                        )
                        file_df['rarity'] = file_df['rarity'].replace(rarities)

                        string_ids = file_df[
                            file_df['group_id'].apply(lambda x: isinstance(x, str))
                        ]['group_id'].unique().tolist()

                        all_cards = get_all_cards()

                        id_mapping = {}
                        if string_ids:
                            for card in all_cards:
                                if card.get('id') in string_ids:
                                    id_mapping[card['id']] = card.get('group_id')

                        valid_group_ids = [
                            c['group_id'] for c in all_cards
                            if c.get('group_id') is not None
                        ]

                        if not valid_group_ids:
                            raise RuntimeError(
                                'Datenbank Rückgabe fehlerhaft oder leer.'
                            )

                        new_group_id = max(valid_group_ids) + 1
                        new_group_ids = []

                        for val in file_df['group_id']:
                            if pd.isna(val):
                                new_group_ids.append(new_group_id)
                                new_group_id += 1
                            elif isinstance(val, str):
                                copy_group_id = id_mapping.get(val, None)
                                if copy_group_id:
                                    new_group_ids.append(copy_group_id)
                                else:
                                    new_group_ids.append(new_group_id)
                                    new_group_id += 1
                            else:
                                new_group_ids.append(val)
                        file_df['group_id'] = new_group_ids

                        st.write('**Vorschau:**')
                        st.dataframe(
                            file_df,
                            column_order=[
                                'id', 'name', 'booster_name',
                                'rarity', 'note', 'group_id'
                            ],
                            column_config={
                                'id': st.column_config.TextColumn('ID'),
                                'name': st.column_config.TextColumn('Name'),
                                'rarity': st.column_config.TextColumn('Seltenheit'),
                                'note': st.column_config.TextColumn('Notiz'),
                                'group_id': st.column_config.NumberColumn('Gruppe'),
                                'booster_name': st.column_config.TextColumn(
                                    'Booster'
                                )
                            },
                            placeholder='-'
                        )

                        st.info(
                            f'Vom Standard abweichende Seltenheiten gefunden: \
                                {", ".join(unmapped_rarities)}'
                        )

                        all_booster = get_booster_data()
                        valid_booster = {row['booster_name'] for row in all_booster}
                        csv_booster = set(file_df['booster_name'].dropna().unique())
                        missing_booster = list(csv_booster - valid_booster)

                        if missing_booster:
                            if len(missing_booster) > 1:
                                st.warning(
                                    f'Es wurden {len(missing_booster)} Booster \
                                        gefunden, die noch nicht existieren.'
                                )
                            else:
                                st.warning(
                                    f'Es wurde {len(missing_booster)} Booster \
                                        gefunden, der noch nicht existiert.'
                                )

                            if st.button(
                                'Booster neu erstellen',
                                icon='🗃️',
                                key='create_new_booster_button'
                            ):
                                booster_creation_dialog(missing_booster)

                        elif st.button(
                            'Karten hinzufügen',
                            icon='🗂️',
                            key='add_new_cards_button'
                        ):
                            file_df = file_df.astype(object) \
                                .where(pd.notnull(file_df), None)
                            records = file_df.to_dict(orient='records')

                            card_upload_response = (
                                supabase.table('cards')
                                .upsert(records)
                                .execute()
                            )

                            if card_upload_response.data:
                                get_all_cards.clear()
                                get_cards_data.clear()
                                get_booster_stats_data.clear()
                                get_sub_booster_stats_data.clear()

                                st.success(
                                    f'{len(card_upload_response.data)} Karten \
                                        erfolgreich hinzugefügt/aktualisiert!'
                                )

                            else:
                                st.error('''
                                    Hinzufügen fehlgeschlagen.
                                    Datenbank Logs überprüfen.
                                ''')

                except Exception as e:
                    st.error(f'Fehler: {e}', icon='❌')


# ----------------------------------------------------------------------------------
# LOGGED OUT

else:
    st.warning('''
        Für die Nutzung dieses Tools ist ein Login in der Seitenleiste notwendig.
    ''')

    if st.session_state.get('authentication_status') is False:
        st.sidebar.error('Benutzername oder Passwort falsch!')
