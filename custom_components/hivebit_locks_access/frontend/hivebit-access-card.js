/*
 * HIVEBIT Access card. Served by the hivebit_locks_access integration.
 * No external dependencies (works with no internet).
 *
 * The card is only a view: every action goes to the integration's WebSocket
 * API, which checks the caller's role. The view itself (owner / family /
 * tablet) is chosen from the role the server reports.
 *
 *   type: custom:hivebit-access-card
 *   entry_id: <optional, defaults to the first lock you have a role on>
 *   view: tablet            # optional: big unlock button only
 */

const CARD_VERSION = "0.2.0";
const NS = "hivebit_locks_access/";

const I18N = {
  en: {
    dir: "ltr",
    lang_switch: "عربي",
    tab_door: "Door", tab_people: "People", tab_codes: "Guest codes", tab_timeline: "Timeline",
    locked: "Locked", unlocked: "Unlocked", unknown_state: "Unknown",
    door_open: "Door open", door_closed: "Door closed", offline: "Lock offline",
    battery: "Battery", hold_to_unlock: "Hold to unlock", tap_to_unlock: "Unlock",
    unlocking: "Unlocking…", unlock_sent: "Unlocked",
    need_name: (n) => `${n} credential${n === 1 ? "" : "s"} need${n === 1 ? "s" : ""} a name`,
    recent: "Recent", see_all: "See all",
    owners: "Authorized persons", family: "Family", household: "Household",
    add_person: "Add person", wall_tablets: "Wall tablets",
    tablets_hint: "HA accounts used by wall tablets. They can unlock, nothing else.",
    save: "Save", cancel: "Cancel", next: "Next", back: "Back", done: "Done", create: "Create",
    close: "Close", remove: "Remove", tap_confirm: "Tap again to confirm",
    remove_person: "Remove person", name: "Name", name_ph: "e.g. Ahmed, Driver, Nanny",
    account: "App account", name_only: "Name only", name_only_hint: "Fingerprint, card or PIN. No app.",
    link_account: "Link an app account", link_hint: "Can also unlock from the app and the tablet.",
    choose_account: "Choose account", owner_toggle: "Authorized person (can manage access)",
    expiry: "Access ends", no_expiry: "No end date", until: "Until",
    add_fingerprint: "Add fingerprint", add_card: "Add card", add_pin: "Add PIN",
    fingerprint: "Fingerprint", card: "Card", pin: "PIN", guest_code: "Guest code", app: "App", tablet: "Tablet",
    enrol_hint_fingerprint: (n) => `Ask ${n} to place the same finger on the lock`,
    enrol_hint_card: (n) => `Ask ${n} to tap the card on the lock`,
    enrol_hint_pin: (n) => `Ask ${n} to type a new PIN on the keypad, twice`,
    waiting_lock: "Waiting for the lock…",
    enrol_done: (w, ref, n) => `${w} #${ref} added to ${n}`,
    enrol_failed: "Enrolment failed", enrol_cancelled: "Enrolment cancelled",
    retry: "Retry", add_another: "Add another",
    credentials: "Credentials", no_credentials: "No fingerprint, card or PIN yet",
    removing: "Removing…", name_this: "Name this", who_is_this: "Who is this?",
    unknown_cred: (w, ref) => `Unknown ${w.toLowerCase()} #${ref}`,
    assign: "Assign", delete_on_lock: "Delete from lock",
    new_code: "New code", code_name_ph: "e.g. Plumber, Cleaner",
    one_time: "One-time", dates: "Dates", weekly: "Weekly",
    h2: "2 h", h24: "24 h", d3: "3 days",
    from: "From", to: "To", days: "Days", daily_from: "Daily from", daily_to: "to", valid_until: "Valid until",
    share: "Share", copy: "Copy", copied: "Copied", revoke: "Revoke",
    ends: (t) => `ends ${t}`, no_codes: "No active guest codes", code_ready: "Code ready",
    load_more: "Load more", all_people: "Everyone", no_events: "Nothing yet",
    notify_arrival: "Tell me when they arrive", edit: "Edit",
    expires_on: (d) => `until ${d}`, badge_app: "App", badge_name_only: "Name only", badge_owner: "Owner",
    reasons: {
      timeout: "The lock timed out. Try again.", duplicate: "Already enrolled on this lock.",
      no_free_id: "The lock is full.", failed: "The lock could not read it. Try again.",
      pin_length: "Wrong PIN length.", pin_not_numeric: "PIN must be digits only.",
    },
    weekdays: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    share_msg: (o) =>
      `Hello ${o.name}, your door code for ${o.lock} is ${o.pin}. Valid ${o.from} – ${o.to}.` +
      (o.once ? " One-time use." : "") + (o.schedule ? ` ${o.schedule}.` : ""),
  },
  ar: {
    dir: "rtl",
    lang_switch: "English",
    tab_door: "الباب", tab_people: "الأشخاص", tab_codes: "رموز الضيوف", tab_timeline: "السجل",
    locked: "مقفل", unlocked: "مفتوح", unknown_state: "غير معروف",
    door_open: "الباب مفتوح", door_closed: "الباب مغلق", offline: "القفل غير متصل",
    battery: "البطارية", hold_to_unlock: "اضغط مطولاً للفتح", tap_to_unlock: "فتح",
    unlocking: "جارٍ الفتح…", unlock_sent: "تم الفتح",
    need_name: (n) => `${n} بحاجة إلى اسم`,
    recent: "الأحدث", see_all: "عرض الكل",
    owners: "المخوَّلون", family: "العائلة", household: "أهل البيت",
    add_person: "إضافة شخص", wall_tablets: "الشاشات الجدارية",
    tablets_hint: "حسابات الشاشات الجدارية. تستطيع الفتح فقط.",
    save: "حفظ", cancel: "إلغاء", next: "التالي", back: "رجوع", done: "تم", create: "إنشاء",
    close: "إغلاق", remove: "حذف", tap_confirm: "اضغط مرة أخرى للتأكيد",
    remove_person: "حذف الشخص", name: "الاسم", name_ph: "مثال: أحمد، السائق، المربية",
    account: "حساب التطبيق", name_only: "اسم فقط", name_only_hint: "بصمة أو بطاقة أو رمز. بدون تطبيق.",
    link_account: "ربط حساب تطبيق", link_hint: "يستطيع الفتح من التطبيق والشاشة أيضاً.",
    choose_account: "اختر الحساب", owner_toggle: "شخص مخوَّل (يدير الدخول)",
    expiry: "ينتهي الدخول", no_expiry: "بدون تاريخ انتهاء", until: "حتى",
    add_fingerprint: "إضافة بصمة", add_card: "إضافة بطاقة", add_pin: "إضافة رمز",
    fingerprint: "بصمة", card: "بطاقة", pin: "رمز", guest_code: "رمز ضيف", app: "التطبيق", tablet: "الشاشة",
    enrol_hint_fingerprint: (n) => `اطلب من ${n} وضع الإصبع نفسه على القفل`,
    enrol_hint_card: (n) => `اطلب من ${n} تمرير البطاقة على القفل`,
    enrol_hint_pin: (n) => `اطلب من ${n} كتابة رمز جديد على لوحة القفل مرتين`,
    waiting_lock: "بانتظار القفل…",
    enrol_done: (w, ref, n) => `تمت إضافة ${w} رقم ${ref} إلى ${n}`,
    enrol_failed: "فشلت الإضافة", enrol_cancelled: "أُلغيت الإضافة",
    retry: "إعادة المحاولة", add_another: "إضافة أخرى",
    credentials: "وسائل الدخول", no_credentials: "لا توجد بصمة أو بطاقة أو رمز بعد",
    removing: "جارٍ الحذف…", name_this: "حدد الاسم", who_is_this: "من هذا؟",
    unknown_cred: (w, ref) => `${w} غير معروفة رقم ${ref}`,
    assign: "تعيين", delete_on_lock: "حذف من القفل",
    new_code: "رمز جديد", code_name_ph: "مثال: سبّاك، عاملة تنظيف",
    one_time: "لمرة واحدة", dates: "تواريخ", weekly: "أسبوعي",
    h2: "ساعتان", h24: "24 ساعة", d3: "3 أيام",
    from: "من", to: "إلى", days: "الأيام", daily_from: "يومياً من", daily_to: "إلى", valid_until: "صالح حتى",
    share: "مشاركة", copy: "نسخ", copied: "تم النسخ", revoke: "إلغاء الرمز",
    ends: (t) => `ينتهي ${t}`, no_codes: "لا توجد رموز ضيوف فعّالة", code_ready: "الرمز جاهز",
    load_more: "المزيد", all_people: "الجميع", no_events: "لا شيء بعد",
    notify_arrival: "أبلغني عند وصوله", edit: "تعديل",
    expires_on: (d) => `حتى ${d}`, badge_app: "تطبيق", badge_name_only: "اسم فقط", badge_owner: "مخوَّل",
    reasons: {
      timeout: "انتهت المهلة. حاول مجدداً.", duplicate: "مسجّلة مسبقاً على هذا القفل.",
      no_free_id: "ذاكرة القفل ممتلئة.", failed: "لم يتمكن القفل من القراءة. حاول مجدداً.",
      pin_length: "طول الرمز غير صحيح.", pin_not_numeric: "الرمز أرقام فقط.",
    },
    weekdays: ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"],
    share_msg: (o) =>
      `مرحباً ${o.name}، رمز باب ${o.lock} هو ${o.pin}. صالح من ${o.from} إلى ${o.to}.` +
      (o.once ? " يُستخدم مرة واحدة." : "") + (o.schedule ? ` ${o.schedule}.` : ""),
  },
};

const METHOD_ICON = {
  fingerprint: "mdi:fingerprint", card: "mdi:card-account-details-outline", pin: "mdi:dialpad",
  guest_code: "mdi:ticket-confirmation-outline", app: "mdi:cellphone", tablet: "mdi:tablet", key: "mdi:key-variant",
};
const KIND_ICON = {
  door: "mdi:door", alarm: "mdi:alert-outline", admin: "mdi:account-cog-outline", offline: "mdi:lan-disconnect",
  online: "mdi:lan-connect", guest_expired: "mdi:timer-off-outline", enrol_outside: "mdi:alert-decagram-outline",
};

const esc = (v) =>
  String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const toLocalInput = (ts) => {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
};
const fromLocalInput = (v) => (v ? Math.floor(new Date(v).getTime() / 1000) : null);

class HivebitAccessCard extends HTMLElement {
  constructor() {
    super();
    this.root = this.attachShadow({ mode: "open" });
    this.s = {
      loading: true, error: null, lock: null, role: null, tab: "door",
      people: null, session: null, codes: null, users: null,
      timeline: [], timelineDone: false, filter: "",
      modal: null, form: {}, confirm: null, toast: null, unlocking: false,
      lang: this._storedLang(),
    };
    this.root.addEventListener("click", (e) => this._onClick(e));
    this.root.addEventListener("input", (e) => this._onInput(e));
    this.root.addEventListener("change", (e) => this._onInput(e));
    this.root.addEventListener("pointerdown", (e) => this._holdStart(e));
    ["pointerup", "pointerleave", "pointercancel"].forEach((t) => this.root.addEventListener(t, () => this._holdEnd()));
  }

  setConfig(config) {
    this._config = config || {};
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._init();
  }

  getCardSize() {
    return 7;
  }

  static getStubConfig() {
    return {};
  }

  disconnectedCallback() {
    if (this._unsub) this._unsub.then((u) => u()).catch(() => {});
    this._unsub = null;
    this._inited = false;
  }

  connectedCallback() {
    if (this._hass && !this._inited) this._init();
  }

  // --- helpers -------------------------------------------------------

  get t() {
    return I18N[this.s.lang] || I18N.en;
  }

  _storedLang() {
    try {
      return localStorage.getItem("hivebit_access_lang") || ((navigator.language || "").startsWith("ar") ? "ar" : "en");
    } catch (_e) {
      return "en";
    }
  }

  get _locale() {
    return this.s.lang === "ar" ? "ar-u-nu-latn" : "en-GB";
  }

  _fmt(ts, opts) {
    return new Intl.DateTimeFormat(this._locale, opts || { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(ts * 1000));
  }

  _ws(type, data = {}) {
    return this._hass.callWS({ type: NS + type, entry_id: this.s.lock?.entry_id, ...data });
  }

  async _run(fn, okMsg) {
    try {
      const r = await fn();
      if (okMsg) this._toast(okMsg);
      return r;
    } catch (err) {
      this._toast(err?.message || String(err), true);
      return undefined;
    }
  }

  _toast(text, error = false) {
    this.s.toast = { text, error };
    this._render();
    clearTimeout(this._toastTimer);
    this._toastTimer = setTimeout(() => {
      this.s.toast = null;
      this._render();
    }, 3500);
  }

  _wordFor(method) {
    return this.t[method] || method;
  }

  _isOwner() {
    return this.s.role === "owner";
  }

  _view() {
    if (this._config?.view === "tablet" || this.s.role === "tablet") return "tablet";
    return this._isOwner() ? "owner" : "family";
  }

  // --- data ----------------------------------------------------------

  async _init() {
    if (this._inited) return;
    this._inited = true;
    try {
      const res = await this._hass.callWS({ type: NS + "locks" });
      const locks = res.locks || [];
      const want = this._config?.entry_id;
      const lock = locks.find((l) => l.entry_id === want) || locks[0];
      if (!lock) {
        this.s.error = "no_lock";
        this.s.loading = false;
        this._render();
        return;
      }
      this.s.lock = lock;
      this.s.role = lock.role;
      this._unsub = this._hass.connection.subscribeMessage((m) => this._onPush(m), {
        type: NS + "subscribe",
        entry_id: lock.entry_id,
      });
      if (this._isOwner()) await Promise.all([this._loadPeople(), this._loadCodes(), this._loadTimeline(true)]);
    } catch (err) {
      this.s.error = err?.message || String(err);
    }
    this.s.loading = false;
    this._render();
  }

  async _loadPeople() {
    const r = await this._ws("people");
    this.s.people = r;
    this.s.session = r.session;
  }

  async _loadCodes() {
    this.s.codes = (await this._ws("guest_codes")).guest_codes;
  }

  async _loadUsers() {
    this.s.users = (await this._ws("ha_users")).users;
  }

  async _loadTimeline(reset) {
    const before = reset ? undefined : this.s.timeline.at(-1)?.seq;
    const r = await this._ws("timeline", { limit: 30, ...(before ? { before_seq: before } : {}) });
    this.s.timeline = reset ? r.entries : [...this.s.timeline, ...r.entries];
    this.s.timelineDone = r.entries.length < 30;
  }

  _onPush(msg) {
    const { topic, data } = msg;
    if (topic === "state") this.s.lock = { ...this.s.lock, ...data };
    else if (topic === "people") this.s.people = { ...data, session: this.s.session };
    else if (topic === "enrol") this.s.session = data.session;
    else if (topic === "guest_codes") this.s.codes = data.guest_codes;
    else if (topic === "timeline" && !this.s.timeline.some((e) => e.seq === data.seq)) this.s.timeline = [data, ...this.s.timeline];
    this._render();
  }

  // --- events --------------------------------------------------------

  _onInput(e) {
    const el = e.target.closest("[data-field]");
    if (!el) return;
    const key = el.dataset.field;
    this.s.form[key] = el.type === "checkbox" ? el.checked : el.value;
    if (el.dataset.rerender !== undefined) this._render();
  }

  _holdStart(e) {
    const el = e.target.closest("[data-hold]");
    if (!el || this.s.unlocking || !this.s.lock?.available) return;
    el.classList.add("holding");
    this._holdEl = el;
    this._holdTimer = setTimeout(() => {
      el.classList.remove("holding");
      this._unlock();
    }, 700);
  }

  _holdEnd() {
    clearTimeout(this._holdTimer);
    this._holdEl?.classList.remove("holding");
    this._holdEl = null;
  }

  _confirmed(key) {
    if (this.s.confirm === key) {
      this.s.confirm = null;
      return true;
    }
    this.s.confirm = key;
    clearTimeout(this._confirmTimer);
    this._confirmTimer = setTimeout(() => {
      this.s.confirm = null;
      this._render();
    }, 3000);
    this._render();
    return false;
  }

  async _unlock() {
    this.s.unlocking = true;
    this._render();
    await this._run(() => this._ws("unlock"), this.t.unlock_sent);
    this.s.unlocking = false;
    this._render();
  }

  async _onClick(e) {
    const el = e.target.closest("[data-action]");
    if (!el) return;
    const a = el.dataset.action;
    const d = el.dataset;
    const s = this.s;
    const t = this.t;
    switch (a) {
      case "lang":
        s.lang = s.lang === "ar" ? "en" : "ar";
        try {
          localStorage.setItem("hivebit_access_lang", s.lang);
        } catch (_e) { /* storage unavailable */ }
        break;
      case "tab":
        s.tab = d.tab;
        if (d.tab === "people" && !s.users) await this._run(() => this._loadUsers());
        break;
      case "unlock":
        if (!s.unlocking && s.lock?.available) await this._unlock();
        return;
      case "close":
        s.modal = null;
        s.form = {};
        break;
      case "add-person":
        if (!s.users) await this._run(() => this._loadUsers());
        s.modal = { type: "wizard", step: 1 };
        s.form = { name: "", mode: "name_only", ha_user_id: "", owner: false, expires: "" };
        break;
      case "wiz-next":
        if (s.modal.step === 1 && !(s.form.name || "").trim()) return this._toast(t.name, true);
        if (s.modal.step === 2 && s.form.mode === "link" && !s.form.ha_user_id) return this._toast(t.choose_account, true);
        s.modal.step += 1;
        break;
      case "wiz-back":
        s.modal.step -= 1;
        break;
      case "wiz-create": {
        const f = s.form;
        const r = await this._run(() =>
          this._ws("person/add", {
            name: f.name.trim(),
            ha_user_id: f.mode === "link" ? f.ha_user_id : null,
            owner: f.mode === "link" && !!f.owner,
            expires_at: f.expires ? fromLocalInput(f.expires) : null,
          })
        );
        if (!r) return;
        s.modal = { type: "person", id: r.person_id, fresh: true };
        await this._run(() => this._loadPeople());
        this._prefillPerson(r.person_id);
        break;
      }
      case "person":
        s.modal = { type: "person", id: d.id };
        if (!s.users) await this._run(() => this._loadUsers());
        this._prefillPerson(d.id);
        break;
      case "person-save": {
        const f = s.form;
        const ok = await this._run(
          () =>
            this._ws("person/update", {
              person_id: s.modal.id,
              name: (f.name || "").trim(),
              ha_user_id: f.ha_user_id || null,
              owner: !!f.owner,
              expires_at: f.expires ? fromLocalInput(f.expires) : null,
              notify_on_arrival: !!f.notify,
            }),
          t.save
        );
        if (ok) s.modal = null;
        break;
      }
      case "person-remove":
        if (!this._confirmed("person-remove")) return;
        if (await this._run(() => this._ws("person/remove", { person_id: s.modal.id }))) s.modal = null;
        break;
      case "enrol": {
        const personId = d.person || s.modal?.id;
        const r = await this._run(() => this._ws("enrol/start", { person_id: personId, method: d.method }));
        if (r) {
          s.session = r.session;
          s.modal = { type: "enrol", person_id: personId, method: d.method };
        }
        break;
      }
      case "enrol-cancel":
        await this._run(() => this._ws("enrol/cancel"));
        break;
      case "enrol-back":
        s.modal = { type: "person", id: s.modal.person_id };
        this._prefillPerson(s.modal.id);
        break;
      case "cred-remove":
        if (!this._confirmed("cred-" + d.id)) return;
        await this._run(() => this._ws("credential/remove", { credential_id: d.id }));
        break;
      case "unknown":
        s.modal = { type: "assign", cred_id: d.id };
        s.form = { person_id: "" };
        break;
      case "assign":
        if (!s.form.person_id) return;
        if (await this._run(() => this._ws("credential/assign", { credential_id: s.modal.cred_id, person_id: s.form.person_id }))) {
          s.modal = null;
          await this._run(() => this._loadTimeline(true));
        }
        break;
      case "unknown-delete":
        if (!this._confirmed("unknown-delete")) return;
        if (await this._run(() => this._ws("credential/remove", { credential_id: s.modal.cred_id }))) s.modal = null;
        break;
      case "tablets-save": {
        const ids = [...this.root.querySelectorAll("[data-tablet]:checked")].map((c) => c.dataset.tablet);
        if (await this._run(() => this._ws("tablets/set", { user_ids: ids }), t.save)) await this._run(() => this._loadUsers());
        break;
      }
      case "new-code":
        s.modal = { type: "code" };
        s.form = { name: "", kind: "one_time", preset: "24", start: toLocalInput(Date.now() / 1000), end: "", days: [], dfrom: "09:00", dto: "12:00" };
        break;
      case "no-expiry":
        s.form.expires = "";
        break;
      case "kind":
        s.form.kind = d.kind;
        break;
      case "preset":
        s.form.preset = d.preset;
        break;
      case "day": {
        const n = Number(d.day);
        const days = new Set(s.form.days || []);
        days.has(n) ? days.delete(n) : days.add(n);
        s.form.days = [...days].sort();
        break;
      }
      case "code-create": {
        const code = await this._createCode();
        if (code) s.modal = { type: "code-done", code };
        break;
      }
      case "share":
        await this._share(this._codeBySlot(Number(d.slot)) || s.modal?.code);
        return;
      case "copy-pin":
        await this._copy(d.pin);
        return;
      case "revoke":
        if (!this._confirmed("revoke-" + d.slot)) return;
        await this._run(() => this._ws("guest_code/revoke", { slot: Number(d.slot) }));
        break;
      case "more":
        await this._run(() => this._loadTimeline(false));
        break;
      case "filter":
        s.filter = d.person || "";
        break;
      default:
        return;
    }
    this._render();
  }

  _prefillPerson(id) {
    const p = this._person(id);
    if (!p) return;
    this.s.form = {
      name: p.name,
      ha_user_id: p.ha_user_id || "",
      owner: p.role === "owner",
      expires: p.expires_at ? toLocalInput(p.expires_at) : "",
      notify: p.notify_on_arrival,
    };
  }

  _person(id) {
    return this.s.people?.people?.find((p) => p.id === id);
  }

  _codeBySlot(slot) {
    return (this.s.codes || []).find((c) => c.slot === slot);
  }

  async _createCode() {
    const f = this.s.form;
    const now = Date.now() / 1000;
    const name = (f.name || "").trim();
    if (!name) {
      this._toast(this.t.name, true);
      return null;
    }
    const msg = { name, kind: f.kind };
    if (f.kind === "one_time") {
      const hours = f.preset === "custom" ? null : Number(f.preset);
      msg.end = hours ? now + hours * 3600 : fromLocalInput(f.end);
    } else if (f.kind === "window") {
      msg.start = fromLocalInput(f.start);
      msg.end = fromLocalInput(f.end);
    } else {
      msg.end = fromLocalInput(f.end);
      msg.weekdays = f.days || [];
      msg.daily_from = (f.dfrom || "09:00").split(":").map(Number);
      msg.daily_to = (f.dto || "12:00").split(":").map(Number);
    }
    return this._run(() => this._ws("guest_code/create", msg));
  }

  _shareText(code) {
    const t = this.t;
    const fmt = (ts) => this._fmt(ts);
    const schedule =
      code.kind === "weekly"
        ? `${code.weekdays.map((i) => t.weekdays[i]).join(", ")} ${code.daily_from.map((n) => String(n).padStart(2, "0")).join(":")}–${code.daily_to.map((n) => String(n).padStart(2, "0")).join(":")}`
        : "";
    const o = { name: code.name, lock: this.s.lock?.name, pin: code.pin, from: fmt(code.start), to: fmt(code.end), once: code.kind === "one_time", schedule };
    const en = I18N.en.share_msg(o);
    const ar = I18N.ar.share_msg(o);
    return this.s.lang === "ar" ? `${ar}\n\n${en}` : `${en}\n\n${ar}`;
  }

  async _share(code) {
    if (!code) return;
    const text = this._shareText(code);
    if (navigator.share) {
      try {
        await navigator.share({ text });
        return;
      } catch (_e) { /* fall back to copy */ }
    }
    await this._copy(text);
  }

  async _copy(text) {
    try {
      await navigator.clipboard.writeText(text);
      this._toast(this.t.copied);
    } catch (_e) {
      this._toast(text);
    }
  }

  // --- rendering -----------------------------------------------------

  _render() {
    const s = this.s;
    const t = this.t;
    let body;
    if (s.loading) body = `<div class="empty">…</div>`;
    else if (s.error === "no_lock") body = `<div class="empty">No lock is shared with this account.</div>`;
    else if (s.error) body = `<div class="empty err">${esc(s.error)}</div>`;
    else {
      const view = this._view();
      if (view === "tablet") body = this._tabletView();
      else if (view === "family") body = this._doorTab(false);
      else body = this._ownerView();
    }
    this.root.innerHTML = `
      <style>${STYLE}</style>
      <ha-card dir="${t.dir}" lang="${s.lang}">
        <div class="wrap ${this._view()}">
          ${this._header()}
          ${body}
        </div>
        ${s.modal ? this._modal() : ""}
        ${s.toast ? `<div class="toast ${s.toast.error ? "err" : ""}">${esc(s.toast.text)}</div>` : ""}
      </ha-card>`;
  }

  _header() {
    const s = this.s;
    const lock = s.lock;
    return `
      <div class="head">
        <div class="brand"><span class="bars"><i></i><i></i><i></i></span><span class="title">${esc(lock?.name || "HIVEBIT")}</span></div>
        <div class="head-right">
          ${lock?.battery != null ? `<span class="muted small batt"><ha-icon icon="mdi:battery"></ha-icon>${lock.battery}%</span>` : ""}
          <button class="link" data-action="lang">${esc(this.t.lang_switch)}</button>
        </div>
      </div>`;
  }

  _status() {
    const lock = this.s.lock || {};
    const t = this.t;
    const state = !lock.available ? "offline" : lock.locked === true ? "locked" : lock.locked === false ? "unlocked" : "unknown";
    const label = state === "offline" ? t.offline : state === "locked" ? t.locked : state === "unlocked" ? t.unlocked : t.unknown_state;
    const door = lock.door_open === true ? t.door_open : lock.door_open === false ? t.door_closed : "";
    const icon = state === "unlocked" ? "mdi:lock-open-variant-outline" : state === "offline" ? "mdi:lock-alert-outline" : "mdi:lock-outline";
    return { state, label, door, icon };
  }

  _doorTab(owner) {
    const t = this.t;
    const s = this.s;
    const st = this._status();
    const unknown = s.people?.unknown?.length || 0;
    const recent = owner ? s.timeline.slice(0, 3) : [];
    return `
      ${owner && unknown ? `<button class="banner" data-action="tab" data-tab="people"><ha-icon icon="mdi:alert-decagram-outline"></ha-icon>${esc(t.need_name(unknown))}</button>` : ""}
      <div class="status ${st.state}">
        <div class="ring"><ha-icon icon="${st.icon}"></ha-icon></div>
        <div class="state">${esc(st.label)}</div>
        <div class="muted">${esc(st.door)}</div>
      </div>
      <button class="unlock ${s.unlocking ? "busy" : ""}" data-hold="unlock" ${s.lock?.available ? "" : "disabled"}>
        <span class="fill"></span><span class="lbl">${esc(s.unlocking ? t.unlocking : t.hold_to_unlock)}</span>
      </button>
      ${owner ? `
        <div class="section-head"><span>${esc(t.recent)}</span><button class="link" data-action="tab" data-tab="timeline">${esc(t.see_all)}</button></div>
        ${recent.length ? `<div class="list">${recent.map((e) => this._eventRow(e)).join("")}</div>` : `<div class="empty small">${esc(t.no_events)}</div>`}` : ""}`;
  }

  _tabletView() {
    const t = this.t;
    const s = this.s;
    const st = this._status();
    return `
      <div class="status big ${st.state}">
        <div class="ring"><ha-icon icon="${st.icon}"></ha-icon></div>
        <div class="state">${esc(st.label)}</div>
        <div class="muted">${esc(st.door)}</div>
      </div>
      <button class="unlock big ${s.unlocking ? "busy" : ""}" data-action="unlock" ${s.lock?.available ? "" : "disabled"}>
        <span class="lbl">${esc(s.unlocking ? t.unlocking : t.tap_to_unlock)}</span>
      </button>`;
  }

  _ownerView() {
    const t = this.t;
    const s = this.s;
    const tabs = [["door", t.tab_door], ["people", t.tab_people], ["codes", t.tab_codes], ["timeline", t.tab_timeline]];
    const content = { door: () => this._doorTab(true), people: () => this._peopleTab(), codes: () => this._codesTab(), timeline: () => this._timelineTab() }[s.tab]();
    return `
      <nav class="tabs">${tabs.map(([k, l]) => `<button class="${s.tab === k ? "on" : ""}" data-action="tab" data-tab="${k}">${esc(l)}</button>`).join("")}</nav>
      <div class="content">${content}</div>`;
  }

  _credChip(c, withRemove) {
    const t = this.t;
    const removing = c.status === "removing";
    return `<span class="chip ${removing ? "dim" : ""}"><ha-icon icon="${METHOD_ICON[c.method] || "mdi:key"}"></ha-icon>${esc(this._wordFor(c.method))} #${c.lock_ref}${removing ? ` · ${esc(t.removing)}` : ""}${
      withRemove && !removing
        ? `<button class="x" data-action="cred-remove" data-id="${c.id}" title="${esc(t.remove)}">${this.s.confirm === "cred-" + c.id ? esc(t.tap_confirm) : "×"}</button>`
        : ""
    }</span>`;
  }

  _peopleTab() {
    const t = this.t;
    const s = this.s;
    const ppl = s.people?.people || [];
    const unknown = s.people?.unknown || [];
    const group = (role, title) => {
      const list = ppl.filter((p) => p.role === role);
      if (!list.length) return "";
      return `<div class="section-head"><span>${esc(title)}</span></div><div class="list">${list
        .map(
          (p) => `
          <button class="row person" data-action="person" data-id="${p.id}">
            <div class="avatar">${esc(p.name.slice(0, 1).toUpperCase())}</div>
            <div class="grow">
              <div class="name">${esc(p.name)} ${p.has_app ? `<span class="badge">${esc(t.badge_app)}</span>` : `<span class="badge dim">${esc(t.badge_name_only)}</span>`}
                ${p.expires_at ? `<span class="badge warn">${esc(t.expires_on(this._fmt(p.expires_at, { day: "numeric", month: "short" })))}</span>` : ""}</div>
              <div class="chips">${p.credentials.length ? p.credentials.map((c) => this._credChip(c, false)).join("") : `<span class="muted small">${esc(t.no_credentials)}</span>`}</div>
            </div>
            <ha-icon class="chev" icon="mdi:chevron-right"></ha-icon>
          </button>`
        )
        .join("")}</div>`;
    };
    const tabletUsers = (s.users || []).filter((u) => !u.linked);
    return `
      ${unknown.length ? `<div class="section-head warn"><span>${esc(t.who_is_this)}</span></div><div class="list">${unknown
        .map((c) => `<button class="row unknown" data-action="unknown" data-id="${c.id}"><ha-icon icon="${METHOD_ICON[c.method]}"></ha-icon><div class="grow">${esc(t.unknown_cred(this._wordFor(c.method), c.lock_ref))}</div><span class="pill">${esc(t.name_this)}</span></button>`)
        .join("")}</div>` : ""}
      <button class="primary wide" data-action="add-person"><ha-icon icon="mdi:account-plus-outline"></ha-icon>${esc(t.add_person)}</button>
      ${group("owner", t.owners)}${group("family", t.family)}${group("household", t.household)}
      <div class="section-head"><span>${esc(t.wall_tablets)}</span></div>
      <div class="panel">
        <div class="muted small">${esc(t.tablets_hint)}</div>
        ${tabletUsers.map((u) => `<label class="check"><input type="checkbox" data-tablet="${u.id}" ${u.tablet ? "checked" : ""}/> ${esc(u.name)}</label>`).join("")}
        <button class="secondary" data-action="tablets-save">${esc(t.save)}</button>
      </div>`;
  }

  _codesTab() {
    const t = this.t;
    const codes = this.s.codes || [];
    const kindLabel = { one_time: t.one_time, window: t.dates, weekly: t.weekly };
    return `
      <button class="primary wide" data-action="new-code"><ha-icon icon="mdi:plus"></ha-icon>${esc(t.new_code)}</button>
      ${codes.length ? `<div class="list">${codes
        .map(
          (c) => `
        <div class="row code">
          <ha-icon icon="mdi:ticket-confirmation-outline"></ha-icon>
          <div class="grow">
            <div class="name">${esc(c.name)} <span class="badge">${esc(kindLabel[c.kind])}</span></div>
            <div class="muted small">${esc(t.ends(this._fmt(c.end)))}${c.kind === "weekly" ? ` · ${c.weekdays.map((i) => esc(t.weekdays[i])).join(", ")}` : ""}</div>
          </div>
          <button class="secondary sm" data-action="share" data-slot="${c.slot}"><ha-icon icon="mdi:share-variant-outline"></ha-icon>${esc(t.share)}</button>
          <button class="ghost sm" data-action="revoke" data-slot="${c.slot}">${esc(this.s.confirm === "revoke-" + c.slot ? t.tap_confirm : t.revoke)}</button>
        </div>`
        )
        .join("")}</div>` : `<div class="empty">${esc(t.no_codes)}</div>`}`;
  }

  _eventRow(e) {
    const icon = e.kind === "unlock" ? METHOD_ICON[e.method] || "mdi:lock-open-variant-outline" : KIND_ICON[e.kind] || "mdi:information-outline";
    return `
      <div class="row event ${e.needs_name ? "attn" : ""}">
        <ha-icon icon="${icon}"></ha-icon>
        <div class="grow"><div>${esc(e.text)}</div><div class="muted small">${esc(this._fmt(e.ts))}</div></div>
        ${e.needs_name && e.credential_id ? `<button class="pill" data-action="unknown" data-id="${e.credential_id}">${esc(this.t.name_this)}</button>` : ""}
      </div>`;
  }

  _timelineTab() {
    const t = this.t;
    const s = this.s;
    const ppl = s.people?.people || [];
    const list = s.filter ? s.timeline.filter((e) => e.person_id === s.filter) : s.timeline;
    return `
      <div class="filters">
        <button class="pill ${s.filter ? "" : "on"}" data-action="filter" data-person="">${esc(t.all_people)}</button>
        ${ppl.map((p) => `<button class="pill ${s.filter === p.id ? "on" : ""}" data-action="filter" data-person="${p.id}">${esc(p.name)}</button>`).join("")}
      </div>
      ${list.length ? `<div class="list">${list.map((e) => this._eventRow(e)).join("")}</div>` : `<div class="empty">${esc(t.no_events)}</div>`}
      ${s.timelineDone ? "" : `<button class="secondary wide" data-action="more">${esc(t.load_more)}</button>`}`;
  }

  // --- modals --------------------------------------------------------

  _modal() {
    const m = this.s.modal;
    const inner = {
      wizard: () => this._wizard(),
      person: () => this._personModal(),
      enrol: () => this._enrolModal(),
      assign: () => this._assignModal(),
      code: () => this._codeModal(),
      "code-done": () => this._codeDoneModal(),
    }[m.type]();
    return `<div class="overlay" dir="${this.t.dir}"><div class="sheet">${inner}</div></div>`;
  }

  _userOptions(selected, allowLinkedId) {
    const t = this.t;
    const users = (this.s.users || []).filter((u) => (!u.linked || u.id === allowLinkedId) && !u.tablet);
    return `<option value="">${esc(t.choose_account)}</option>${users
      .map((u) => `<option value="${u.id}" ${u.id === selected ? "selected" : ""}>${esc(u.name)}</option>`)
      .join("")}`;
  }

  _wizard() {
    const t = this.t;
    const f = this.s.form;
    const step = this.s.modal.step;
    const dots = [1, 2, 3].map((n) => `<i class="${n <= step ? "on" : ""}"></i>`).join("");
    let body = "";
    if (step === 1) {
      body = `<label class="field"><span>${esc(t.name)}</span><input data-field="name" value="${esc(f.name)}" placeholder="${esc(t.name_ph)}" maxlength="40" autofocus/></label>`;
    } else if (step === 2) {
      body = `
        <label class="option ${f.mode === "name_only" ? "on" : ""}"><input type="radio" name="mode" value="name_only" data-field="mode" data-rerender ${f.mode === "name_only" ? "checked" : ""}/>
          <div><div class="name">${esc(t.name_only)}</div><div class="muted small">${esc(t.name_only_hint)}</div></div></label>
        <label class="option ${f.mode === "link" ? "on" : ""}"><input type="radio" name="mode" value="link" data-field="mode" data-rerender ${f.mode === "link" ? "checked" : ""}/>
          <div><div class="name">${esc(t.link_account)}</div><div class="muted small">${esc(t.link_hint)}</div></div></label>
        ${f.mode === "link" ? `
          <label class="field"><span>${esc(t.account)}</span><select data-field="ha_user_id">${this._userOptions(f.ha_user_id)}</select></label>
          <label class="check"><input type="checkbox" data-field="owner" ${f.owner ? "checked" : ""}/> ${esc(t.owner_toggle)}</label>` : ""}`;
    } else {
      body = `
        <button class="option ${!f.expires ? "on" : ""}" data-action="no-expiry"><input type="radio" tabindex="-1" ${!f.expires ? "checked" : ""}/><div class="name">${esc(t.no_expiry)}</div></button>
        <label class="field"><span>${esc(t.until)}</span><input type="datetime-local" data-field="expires" data-rerender value="${esc(f.expires)}"/></label>`;
    }
    return `
      <div class="sheet-head"><div class="title">${esc(t.add_person)}</div><div class="dots">${dots}</div><button class="link" data-action="close">${esc(t.cancel)}</button></div>
      ${step === 3 ? `<div class="muted">${esc(t.expiry)}</div>` : ""}
      <div class="sheet-body">${body}</div>
      <div class="sheet-foot">
        ${step > 1 ? `<button class="secondary" data-action="wiz-back">${esc(t.back)}</button>` : "<span></span>"}
        ${step < 3 ? `<button class="primary" data-action="wiz-next">${esc(t.next)}</button>` : `<button class="primary" data-action="wiz-create">${esc(t.create)}</button>`}
      </div>`;
  }

  _enrolButtons(personId) {
    const t = this.t;
    const methods = this.s.lock?.capabilities?.enrol_methods || [];
    const lbl = { fingerprint: t.add_fingerprint, card: t.add_card, pin: t.add_pin };
    return `<div class="enrol-buttons">${["fingerprint", "card", "pin"]
      .filter((m) => methods.includes(m))
      .map((m) => `<button class="tile" data-action="enrol" data-method="${m}" data-person="${personId}"><ha-icon icon="${METHOD_ICON[m]}"></ha-icon><span>${esc(lbl[m])}</span></button>`)
      .join("")}</div>`;
  }

  _personModal() {
    const t = this.t;
    const s = this.s;
    const p = this._person(s.modal.id);
    if (!p) return `<div class="sheet-head"><div class="title"></div><button class="link" data-action="close">${esc(t.close)}</button></div>`;
    const f = s.form;
    return `
      <div class="sheet-head"><div class="title">${esc(p.name)}</div><button class="link" data-action="close">${esc(t.close)}</button></div>
      <div class="sheet-body">
        <div class="section-head"><span>${esc(t.credentials)}</span></div>
        <div class="chips">${p.credentials.length ? p.credentials.map((c) => this._credChip(c, true)).join("") : `<span class="muted small">${esc(t.no_credentials)}</span>`}</div>
        ${this._enrolButtons(p.id)}
        <div class="section-head"><span>${esc(t.edit)}</span></div>
        <label class="field"><span>${esc(t.name)}</span><input data-field="name" value="${esc(f.name)}" maxlength="40"/></label>
        <label class="field"><span>${esc(t.account)}</span><select data-field="ha_user_id">${this._userOptions(f.ha_user_id, p.ha_user_id).replace(`>${esc(t.choose_account)}<`, `>${esc(t.name_only)}<`)}</select></label>
        <label class="check"><input type="checkbox" data-field="owner" ${f.owner ? "checked" : ""}/> ${esc(t.owner_toggle)}</label>
        <label class="field"><span>${esc(t.expiry)}</span><input type="datetime-local" data-field="expires" value="${esc(f.expires)}"/></label>
        <label class="check"><input type="checkbox" data-field="notify" ${f.notify ? "checked" : ""}/> ${esc(t.notify_arrival)}</label>
      </div>
      <div class="sheet-foot">
        <button class="danger" data-action="person-remove">${esc(s.confirm === "person-remove" ? t.tap_confirm : t.remove_person)}</button>
        <button class="primary" data-action="person-save">${esc(t.save)}</button>
      </div>`;
  }

  _enrolModal() {
    const t = this.t;
    const s = this.s;
    const m = s.modal;
    const ses = s.session && s.session.person_id === m.person_id ? s.session : null;
    const name = this._person(m.person_id)?.name || "";
    const state = ses?.state || "waiting";
    const needed = ses?.presses_needed || (m.method === "fingerprint" ? 4 : m.method === "pin" ? 2 : 1);
    const done = ses?.presses_done || 0;
    const pct = state === "done" ? 1 : Math.min(1, done / needed);
    const C = 2 * Math.PI * 54;
    let line;
    if (state === "done") line = t.enrol_done(this._wordFor(m.method), ses.lock_ref, name);
    else if (state === "failed") line = `${t.enrol_failed}. ${t.reasons[ses.reason] || ses.reason || ""}`;
    else if (state === "cancelled") line = t.enrol_cancelled;
    else if (state === "waiting") line = t.waiting_lock;
    else line = `${done} / ${needed}`;
    const open = state === "waiting" || state === "enrolling";
    return `
      <div class="sheet-head"><div class="title">${esc(name)}</div></div>
      <div class="sheet-body center">
        <svg class="progress ${state}" viewBox="0 0 120 120">
          <circle cx="60" cy="60" r="54" class="track"/>
          <circle cx="60" cy="60" r="54" class="bar" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct)}"/>
        </svg>
        <ha-icon class="enrol-icon ${state}" icon="${state === "done" ? "mdi:check" : state === "failed" ? "mdi:close" : METHOD_ICON[m.method]}"></ha-icon>
        <div class="hint">${esc(t["enrol_hint_" + m.method](name))}</div>
        <div class="state-line ${state}">${esc(line)}</div>
      </div>
      <div class="sheet-foot">
        ${open ? `<button class="secondary" data-action="enrol-cancel">${esc(t.cancel)}</button><span></span>` : `
          <button class="secondary" data-action="enrol-back">${esc(t.done)}</button>
          ${state === "done" ? `<button class="primary" data-action="enrol-back">${esc(t.add_another)}</button>` : `<button class="primary" data-action="enrol" data-method="${m.method}" data-person="${m.person_id}">${esc(t.retry)}</button>`}`}
      </div>`;
  }

  _assignModal() {
    const t = this.t;
    const s = this.s;
    const cred = [...(s.people?.unknown || [])].find((c) => c.id === s.modal.cred_id);
    const title = cred ? t.unknown_cred(this._wordFor(cred.method), cred.lock_ref) : t.who_is_this;
    const ppl = s.people?.people || [];
    return `
      <div class="sheet-head"><div class="title">${esc(title)}</div><button class="link" data-action="close">${esc(t.close)}</button></div>
      <div class="sheet-body">
        <div class="muted">${esc(t.who_is_this)}</div>
        <label class="field"><select data-field="person_id"><option value="">—</option>${ppl.map((p) => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select></label>
      </div>
      <div class="sheet-foot">
        <button class="danger" data-action="unknown-delete">${esc(s.confirm === "unknown-delete" ? t.tap_confirm : t.delete_on_lock)}</button>
        <button class="primary" data-action="assign">${esc(t.assign)}</button>
      </div>`;
  }

  _codeModal() {
    const t = this.t;
    const f = this.s.form;
    const kinds = [["one_time", t.one_time], ["window", t.dates], ["weekly", t.weekly]];
    let opts = "";
    if (f.kind === "one_time") {
      opts = `<div class="seg">${[["2", t.h2], ["24", t.h24], ["72", t.d3], ["custom", "…"]]
        .map(([v, l]) => `<button class="${f.preset === v ? "on" : ""}" data-action="preset" data-preset="${v}">${esc(l)}</button>`)
        .join("")}</div>
        ${f.preset === "custom" ? `<label class="field"><span>${esc(t.valid_until)}</span><input type="datetime-local" data-field="end" value="${esc(f.end)}"/></label>` : ""}`;
    } else if (f.kind === "window") {
      opts = `<label class="field"><span>${esc(t.from)}</span><input type="datetime-local" data-field="start" value="${esc(f.start)}"/></label>
        <label class="field"><span>${esc(t.to)}</span><input type="datetime-local" data-field="end" value="${esc(f.end)}"/></label>`;
    } else {
      opts = `<div class="muted small">${esc(t.days)}</div><div class="seg days">${t.weekdays
        .map((w, i) => `<button class="${(f.days || []).includes(i) ? "on" : ""}" data-action="day" data-day="${i}">${esc(w.slice(0, this.s.lang === "ar" ? 3 : 2))}</button>`)
        .join("")}</div>
        <div class="row2"><label class="field"><span>${esc(t.daily_from)}</span><input type="time" data-field="dfrom" value="${esc(f.dfrom)}"/></label>
        <label class="field"><span>${esc(t.daily_to)}</span><input type="time" data-field="dto" value="${esc(f.dto)}"/></label></div>
        <label class="field"><span>${esc(t.valid_until)}</span><input type="datetime-local" data-field="end" value="${esc(f.end)}"/></label>`;
    }
    return `
      <div class="sheet-head"><div class="title">${esc(t.new_code)}</div><button class="link" data-action="close">${esc(t.cancel)}</button></div>
      <div class="sheet-body">
        <label class="field"><span>${esc(t.name)}</span><input data-field="name" value="${esc(f.name)}" placeholder="${esc(t.code_name_ph)}" maxlength="40"/></label>
        <div class="seg">${kinds.map(([k, l]) => `<button class="${f.kind === k ? "on" : ""}" data-action="kind" data-kind="${k}">${esc(l)}</button>`).join("")}</div>
        ${opts}
      </div>
      <div class="sheet-foot"><span></span><button class="primary" data-action="code-create">${esc(t.create)}</button></div>`;
  }

  _codeDoneModal() {
    const t = this.t;
    const c = this.s.modal.code;
    return `
      <div class="sheet-head"><div class="title">${esc(t.code_ready)}</div><button class="link" data-action="close">${esc(t.done)}</button></div>
      <div class="sheet-body center">
        <div class="muted">${esc(c.name)}</div>
        <div class="pin" dir="ltr">${esc(c.pin.slice(0, 3))} ${esc(c.pin.slice(3))}</div>
        <div class="muted small">${esc(this._fmt(c.start))} – ${esc(this._fmt(c.end))}</div>
      </div>
      <div class="sheet-foot">
        <button class="secondary" data-action="copy-pin" data-pin="${esc(c.pin)}">${esc(t.copy)}</button>
        <button class="primary" data-action="share"><ha-icon icon="mdi:share-variant-outline"></ha-icon>${esc(t.share)}</button>
      </div>`;
  }
}

const STYLE = `
  :host { --gold:#E8D1B3; --gold2:#C7B299; --txt:#E8E2D8; --txt2:#9b9488; --line:#26231f; --surf:rgba(232,209,179,.05);
          --surf2:rgba(232,209,179,.10); --accent:#FFA500; --danger:#e5735f; --ok:#9cc89a; display:block; }
  ha-card { display:block; background: var(--hb-card-bg, #0b0b0b); color: var(--txt); border: 1px solid var(--line); border-radius: 18px; overflow: hidden; position: relative; font-size: 15px; }
  .wrap { padding: 16px; display:flex; flex-direction:column; gap:14px; }
  ha-icon { --mdc-icon-size: 20px; display:inline-flex; }
  button { font: inherit; color: inherit; background: none; border: 0; cursor: pointer; }
  button:disabled { opacity:.4; cursor: default; }
  .head { display:flex; align-items:center; justify-content:space-between; }
  .brand { display:flex; align-items:center; gap:10px; }
  .bars { display:inline-flex; flex-direction:column; gap:3px; }
  .bars i { display:block; width:16px; height:3px; border-radius:2px; background: var(--gold); }
  .title { font-weight:600; letter-spacing:.02em; color: var(--gold); font-size:17px; }
  .head-right { display:flex; align-items:center; gap:12px; }
  .batt { display:inline-flex; align-items:center; gap:4px; }
  .muted { color: var(--txt2); } .small { font-size: 13px; }
  .link { color: var(--gold2); font-size: 14px; padding: 4px 2px; }
  .tabs { display:flex; gap:4px; background: var(--surf); border-radius: 12px; padding: 4px; }
  .tabs button { flex:1; padding: 9px 4px; border-radius: 9px; font-size: 13.5px; color: var(--txt2); white-space: nowrap; }
  .tabs button.on { background: var(--surf2); color: var(--gold); font-weight:600; }
  .content { display:flex; flex-direction:column; gap:12px; }
  .status { display:flex; flex-direction:column; align-items:center; gap:6px; padding: 18px 0 6px; }
  .ring { width:96px; height:96px; border-radius:50%; display:flex; align-items:center; justify-content:center; border:2px solid var(--gold2); color: var(--gold); }
  .ring ha-icon { --mdc-icon-size: 44px; }
  .status.unlocked .ring { border-color: var(--accent); color: var(--accent); box-shadow: 0 0 0 6px rgba(255,165,0,.10); }
  .status.offline .ring, .status.unknown .ring { border-color: #555; color: #777; }
  .state { font-size: 22px; font-weight: 600; color: var(--gold); }
  .status.unlocked .state { color: var(--accent); }
  .status.big .ring { width:160px; height:160px; } .status.big .ring ha-icon { --mdc-icon-size: 76px; } .status.big .state { font-size: 32px; }
  .unlock { position:relative; overflow:hidden; height:56px; border-radius: 28px; border:1px solid var(--gold2); color: var(--gold); font-weight:600; touch-action:none; user-select:none; }
  .unlock .fill { position:absolute; inset:0; width:0; background: rgba(255,165,0,.22); transition: width 0s; }
  .unlock.holding .fill { width:100%; transition: width .7s linear; }
  .unlock .lbl { position:relative; }
  .unlock.big { height: 96px; border-radius: 48px; font-size: 26px; background: var(--surf2); }
  .unlock.busy { opacity:.6; }
  .banner { display:flex; gap:8px; align-items:center; padding: 10px 12px; border-radius: 12px; background: rgba(255,165,0,.12); color: var(--accent); font-weight:600; text-align:start; }
  .section-head { display:flex; justify-content:space-between; align-items:center; color: var(--txt2); font-size: 12.5px; text-transform: uppercase; letter-spacing: .06em; margin-top: 4px; }
  .section-head.warn { color: var(--accent); }
  .list { display:flex; flex-direction:column; border:1px solid var(--line); border-radius: 14px; overflow:hidden; }
  .row { display:flex; align-items:center; gap:12px; padding: 11px 12px; text-align:start; border-bottom:1px solid var(--line); width:100%; box-sizing:border-box; }
  .row:last-child { border-bottom:0; }
  .row > ha-icon { color: var(--gold2); flex: none; }
  .row.attn, .row.unknown { background: rgba(255,165,0,.07); } .row.unknown > ha-icon, .row.attn > ha-icon { color: var(--accent); }
  .grow { flex:1; min-width:0; display:flex; flex-direction:column; gap:3px; }
  .name { font-weight: 600; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .avatar { width:38px; height:38px; border-radius:50%; background: var(--surf2); color: var(--gold); display:flex; align-items:center; justify-content:center; font-weight:600; flex:none; }
  .chev { color:#555; } [dir=rtl] .chev { transform: scaleX(-1); }
  .badge { font-size: 11px; font-weight:600; padding: 2px 7px; border-radius: 10px; background: var(--surf2); color: var(--gold2); }
  .badge.dim { color: var(--txt2); background: rgba(255,255,255,.05); } .badge.warn { color: var(--accent); background: rgba(255,165,0,.12); }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { display:inline-flex; align-items:center; gap:5px; font-size: 12.5px; padding: 4px 9px; border-radius: 14px; background: var(--surf); color: var(--txt); }
  .chip ha-icon { --mdc-icon-size: 15px; color: var(--gold2); } .chip.dim { opacity:.55; }
  .chip .x { color: var(--danger); padding: 0 2px; font-size: 13px; }
  .pill { font-size: 12.5px; padding: 5px 11px; border-radius: 14px; border:1px solid var(--line); color: var(--gold2); white-space:nowrap; }
  .pill.on { background: var(--surf2); color: var(--gold); border-color: transparent; }
  .row .pill { color: var(--accent); border-color: rgba(255,165,0,.4); }
  .filters { display:flex; gap:6px; overflow-x:auto; padding-bottom:2px; }
  .primary, .secondary, .danger, .ghost { display:inline-flex; align-items:center; justify-content:center; gap:6px; padding: 11px 16px; border-radius: 12px; font-weight:600; }
  .primary { background: var(--gold); color: #141210; } .secondary { background: var(--surf2); color: var(--gold); }
  .danger { color: var(--danger); background: rgba(229,115,95,.10); } .ghost { color: var(--txt2); }
  .wide { width:100%; } .sm { padding: 7px 10px; font-size: 13px; } .sm ha-icon { --mdc-icon-size: 16px; }
  .panel { display:flex; flex-direction:column; gap:8px; padding: 12px; border:1px solid var(--line); border-radius: 14px; }
  .check { display:flex; align-items:center; gap:10px; padding: 4px 0; }
  .empty { text-align:center; color: var(--txt2); padding: 22px 8px; } .empty.err { color: var(--danger); }
  .overlay { position:fixed; inset:0; background: rgba(0,0,0,.72); display:flex; align-items:flex-end; justify-content:center; z-index: 5; }
  .sheet { width:100%; max-width: 520px; max-height: 92vh; overflow:auto; background:#121110; border-top:1px solid var(--line); border-radius: 18px 18px 0 0; padding: 16px; box-sizing:border-box; display:flex; flex-direction:column; gap:14px; }
  .sheet-head { display:flex; align-items:center; justify-content:space-between; gap:10px; }
  .sheet-body { display:flex; flex-direction:column; gap:12px; } .sheet-body.center { align-items:center; text-align:center; position:relative; }
  .sheet-foot { display:flex; justify-content:space-between; gap:10px; }
  .dots { display:flex; gap:5px; } .dots i { width:7px; height:7px; border-radius:50%; background:#3a3631; } .dots i.on { background: var(--gold); }
  .field { display:flex; flex-direction:column; gap:6px; font-size: 13px; color: var(--txt2); flex:1; }
  input, select { font: inherit; font-size: 15px; color: var(--txt); background: #1b1917; border:1px solid #2f2b27; border-radius: 10px; padding: 11px 12px; color-scheme: dark; }
  input:focus, select:focus { outline: 1px solid var(--gold2); }
  input[type=checkbox], input[type=radio] { width:18px; height:18px; accent-color: var(--gold); padding:0; }
  .option { display:flex; gap:12px; align-items:flex-start; padding: 12px; border:1px solid var(--line); border-radius: 12px; }
  .option.on { border-color: var(--gold2); background: var(--surf); }
  .seg { display:flex; gap:4px; background: var(--surf); padding:4px; border-radius: 11px; }
  .seg button { flex:1; padding: 8px 4px; border-radius: 8px; color: var(--txt2); font-size: 13.5px; }
  .seg button.on { background: var(--surf2); color: var(--gold); font-weight: 600; }
  .row2 { display:flex; gap:10px; }
  .enrol-buttons { display:grid; grid-template-columns: repeat(3, 1fr); gap:8px; }
  .tile { display:flex; flex-direction:column; align-items:center; gap:6px; padding: 14px 6px; border-radius: 12px; background: var(--surf); color: var(--gold); font-size: 13px; font-weight:600; }
  .tile ha-icon { --mdc-icon-size: 28px; }
  .progress { width: 150px; height: 150px; transform: rotate(-90deg); }
  .progress circle { fill:none; stroke-width: 6; } .progress .track { stroke: #2a2723; }
  .progress .bar { stroke: var(--gold); stroke-linecap: round; transition: stroke-dashoffset .4s ease; }
  .progress.done .bar { stroke: var(--ok); } .progress.failed .bar { stroke: var(--danger); }
  .enrol-icon { position:absolute; top: 51px; left: 50%; transform: translateX(-50%); --mdc-icon-size: 48px; color: var(--gold); }
  .enrol-icon.done { color: var(--ok); } .enrol-icon.failed { color: var(--danger); }
  .hint { font-size: 15px; max-width: 280px; } .state-line { font-weight:600; color: var(--gold); } .state-line.failed { color: var(--danger); } .state-line.done { color: var(--ok); }
  .pin { font-size: 40px; font-weight: 700; letter-spacing: .12em; color: var(--gold); font-variant-numeric: tabular-nums; }
  .toast { position:fixed; left: 12px; right: 12px; bottom: 16px; max-width: 496px; margin: 0 auto; padding: 11px 14px; border-radius: 12px; background: #24211d; color: var(--txt); z-index: 6; white-space: pre-line; }
  .toast.err { background: #3a1f1a; color: #f4c3b8; }
`;

if (!customElements.get("hivebit-access-card")) {
  customElements.define("hivebit-access-card", HivebitAccessCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "hivebit-access-card",
    name: "HIVEBIT Access",
    description: "Door, people, guest codes and timeline for HIVEBIT Locks Access.",
  });
  console.info(`%c HIVEBIT-ACCESS-CARD %c ${CARD_VERSION} `, "background:#E8D1B3;color:#000", "background:#000;color:#E8D1B3");
}
