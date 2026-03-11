## Simple guide: why and when to use `live_method`

### 1. Normal pages vs live pages

**Normal page flow**

- User sees a page, fills a form, clicks “Next”.
- oTree does a single HTTP POST:
  - Saves form fields into `player`, `group`, or `subsession`.
  - Immediately moves to the next page.
- Good for:
  - One shot questions.
  - Simple decisions with no real time feedback.

**Live pages with `live_method`**

- The page stays visible.
- The browser can send **multiple small messages** while the participant remains on that page.
- Each message calls:

```python
@staticmethod
def live_method(player, data):
    # data is a dict sent from JS, e.g. {'message': 'hello'}
    ...
```

- You can process `data`, update variables, and send a response back, without leaving the page.

---

### 2. Why we use `live_method`

We use `live_method` when we need **real time interaction** instead of a single submit:

- **Chat style interaction** with an LLM:
  - User types a message.
  - JS sends `{ "message": "..." }` to `live_method`.
  - Server calls the LLM and returns the reply.
  - JS shows the reply, and the user can send another message.

- **Interactive JS behavior** that needs server feedback during the page:
  - For example: sliders changing a preview, or dynamic hints.

- **Multiple back and forths** on the same screen:
  - The participant does not advance to the next page yet.
  - You can accumulate state (like `conversation_history`) and only finalize it in `before_next_page`.

If you only need one submit and then move on, a normal page with `form_model` and `form_fields` is enough.  
If you want a **live conversation** or repeated updates while the page is open, you use `live_method`.

---

### 3. Why “WebSocket, like chat or JS messages”

Internally, oTree implements these “live” messages using a WebSocket style mechanism:

- Your JavaScript calls something like:

```javascript
liveSend({ message: 'hello' });
```

- oTree delivers that to:

```python
@staticmethod
def live_method(player, data):
    user_message = data.get('message')
    ...
    return {player.id_in_group: {'response': reply_text}}
```

- If `live_method` returns a dict, oTree sends it back to the browser, and your JS can:
  - insert the reply into the chat log,
  - update the UI,
  - etc.

This pattern is exactly what we want for:

- Chat with an LLM,
- Real time assistants,
- Any other **JS driven, interactive page** where data flows back and forth while the page is still on screen.

