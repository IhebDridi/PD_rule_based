## Simple guide: input and output in oTree pages

### 1. Getting input from the user

**Normal (non-live) pages**

- **Step 1 – Declare where to store form fields:**

```python
class MyPage(Page):
    form_model = 'player'          # or 'group', 'subsession'
    form_fields = ['my_field']     # fields defined on Player
```

- **Step 2 – Define the field on `Player` in `models.py`:**

```python
class Player(BasePlayer):
    my_field = models.StringField()
```

- **What happens:**  
  When the user types something and clicks “Next”, oTree automatically saves the value into `self.player.my_field`.

---

**Live pages (WebSocket, like chat or JS messages)**

- **Step 1 – Define a `live_method` on the page:**

```python
class MyLivePage(Page):
    @staticmethod
    def live_method(player, data):
        # data is a dict sent from JS, e.g. {'message': 'hello'}
        user_message = data.get('message')
        ...
```

- **What happens:**  
  Your JS sends a JSON object; `data` receives it; you read `data[...]` to get input.

---

### 2. Sending output to the page (template)

- **Use `vars_for_template` to pass values into the HTML:**

```python
class MyPage(Page):
    def vars_for_template(self):
        return {
            'greeting': "Hello",
            'round_number': self.round_number,
        }
```

- **In the template `MyPage.html`:**

```html
<p>{{ greeting }}, this is round {{ round_number }}</p>
```

- **What happens:**  
  Values in the dict from `vars_for_template` are available as template variables.

---

### 3. Storing / updating values in user variables

There are three main places to store things:

#### 3.1 On the current `Player` (per round, per participant)

- **Example – after form submission:**

```python
class MyPage(Page):
    def before_next_page(self):
        # self.player.my_field already has the form value
        self.player.some_other_field = "extra info"
```

- Use when the value belongs to **this participant in this round**.

---

#### 3.2 On `participant.vars` (persists across rounds and apps)

- **Example – remember a setting across the whole session:**

```python
class MyPage(Page):
    def before_next_page(self):
        self.participant.vars['strategy'] = self.player.my_field
```

- Later, in another page:

```python
strategy = self.participant.vars.get('strategy')
```

- Use when the value belongs to **this participant, all rounds**.

---

#### 3.3 On `session.vars` (shared across all participants)

- **Example – store a global list:**

```python
def before_next_page(self):
    lobby = self.session.vars.get('lobby_ids', [])
    lobby.append(self.participant.id_in_session)
    self.session.vars['lobby_ids'] = lobby
```

- Use when data is **shared across many participants**.

---

### 4. Summary in one sentence

- **Input from user**: `form_model` + `form_fields` (or `live_method` with `data`).  
- **Output to page**: return a dict in `vars_for_template` and use its keys in the HTML.  
- **Save/update values**: write to `self.player.<field>`, `self.participant.vars[...]`, or `self.session.vars[...]` (depending on scope).

