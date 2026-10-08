const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

function loadModel(name) {
  const file = path.resolve(__dirname, "../../src/features", name, "model.ts");
  const code = ts.transpileModule(fs.readFileSync(file, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  const exports = {};
  new Function("exports", code)(exports);
  return exports;
}

const { recordId, responseIsOpen, needsFinalResponse, checkInIsOpen, eventIsArchived, sameDayInTimezone, schedulePeriod, eventInPeriod } = loadModel("schedule");
const { safeAppLink, notificationDestination } = loadModel("notifications");
const { filterAppeals, messageDraftKey, validMessageBody } = loadModel("appeals");
const { filterMaterials, learningProgress } = loadModel("learning");
const now = Date.parse("2026-10-08T10:00:00Z");
const event = { requires_response: true, status_code: "PLANNED", start_datetime: "2026-10-08T12:00:00Z", response_deadline_at: "2026-10-08T11:00:00Z" };

test("response closes on cancellation, start, and participant deadline", () => {
  assert.equal(responseIsOpen(event, 3, now), true);
  for (const value of [{ status_code: "CANCELLED" }, { start_datetime: new Date(now).toISOString() }, { requires_response: false }, { response_deadline_at: "2026-10-08T09:00:00Z" }]) {
    assert.equal(responseIsOpen({ ...event, ...value }, 3, now), false);
  }
});
test("commander deadline override still respects cancellation and start", () => {
  assert.equal(responseIsOpen({ ...event, response_deadline_at: "2026-10-08T09:00:00Z" }, 4, now), true);
  assert.equal(responseIsOpen({ ...event, status_code: "CANCELLED" }, 9, now), false);
});
test("MAYBE remains in the list requiring a final answer", () => {
  for (const code of [undefined, null, "MAYBE"]) assert.equal(needsFinalResponse({ ...event, my_response_code: code }), true);
  for (const code of ["COMING", "NOT_COMING"]) assert.equal(needsFinalResponse({ ...event, my_response_code: code }), false);
});
test("record links reject malformed, negative, and unsafe IDs", () => {
  assert.equal(recordId("?event=123", "event"), 123);
  for (const query of ["", "?event=0", "?event=-1", "?event=1.5", "?event=1e2", "?event=9007199254740993"]) assert.equal(recordId(query, "event"), null);
});
test("internal navigation keeps the query and blocks external destinations", () => {
  assert.equal(safeAppLink("/schedule?event=3"), "/schedule?event=3");
  for (const link of ["https://evil.example/", "//evil.example/", "/\\evil.example/", "javascript:alert(1)", "/unknown"]) assert.equal(safeAppLink(link), null);
});
test("notifications without a deep link still lead to the related record", () => {
  assert.equal(notificationDestination({ entity_name: "appeals", entity_id: 4 }), "/appeals?id=4");
  assert.equal(notificationDestination({ entity_name: "schedule_events", entity_id: 7 }), "/schedule?event=7");
  assert.equal(notificationDestination({ entity_name: "unknown", entity_id: 7 }), null);
});
test("submission IDs are not mistaken for normative IDs", () => {
  assert.equal(notificationDestination({ entity_name: "normative_submissions", entity_id: 8, deep_link: "/normatives?id=8" }), "/normatives");
});
test("explicit safe destination is preserved; hostile link uses local fallback", () => {
  assert.equal(notificationDestination({ deep_link: "/learning?material=4" }), "/learning?material=4");
  assert.equal(notificationDestination({ deep_link: "//evil.example", entity_name: "appeals", entity_id: 5 }), "/appeals?id=5");
});

test("ongoing class stays visible while check-in remains open", () => {
  const ongoing = { ...event, self_checkin_enabled: true, start_datetime: "2026-10-08T09:50:00Z", end_datetime: null };
  assert.equal(checkInIsOpen(ongoing, now), true);
  assert.equal(eventIsArchived(ongoing, now), false);
  assert.equal(eventIsArchived(ongoing, now + 21 * 60_000), true);
});
test("check-in respects explicit boundaries and cancellation", () => {
  const item = { ...event, self_checkin_enabled: true, self_checkin_opens_at: "2026-10-08T10:00:00Z", self_checkin_closes_at: "2026-10-08T10:01:00Z" };
  assert.equal(checkInIsOpen(item, now), true);
  assert.equal(checkInIsOpen(item, now - 1), false);
  assert.equal(checkInIsOpen(item, now + 60_001), false);
  assert.equal(checkInIsOpen({ ...item, status_code: "CANCELLED" }, now), false);
});
test("today uses the club timezone near the midnight boundary", () => {
  assert.equal(sameDayInTimezone("2026-10-08T18:00:00Z", Date.parse("2026-10-08T16:00:00Z"), "Asia/Novosibirsk"), false);
  assert.equal(sameDayInTimezone("2026-10-08T18:00:00Z", Date.parse("2026-10-08T17:00:00Z"), "Asia/Novosibirsk"), true);
});

test("appeal search combines status, case-insensitive text and number", () => {
  const rows = [
    { id: 1, subject: "Расписание", description: "Изменить время", status_code: "CREATED", created_at: "2026-10-07" },
    { id: 2, subject: "Тренировка", description: "РАСПИСАНИЕ изменилось", status_code: "IN_PROGRESS", created_at: "2026-10-06", updated_at: "2026-10-08" },
  ];
  assert.deepEqual(filterAppeals(rows, "  расписание  ", "").map((item) => item.id), [2, 1]);
  assert.deepEqual(filterAppeals(rows, "расписание", "CREATED").map((item) => item.id), [1]);
  assert.deepEqual(filterAppeals(rows, "2", "").map((item) => item.id), [2]);
  assert.equal(filterAppeals(rows, "нет совпадений", "").length, 0);
  assert.deepEqual(rows.map((item) => item.id), [1, 2]);
});
test("appeal sort remains stable when timestamps match", () => {
  const rows = [1, 2].map((id) => ({ id, subject: "Тема", description: "Текст", status_code: "CREATED", created_at: "2026-10-08" }));
  assert.deepEqual(filterAppeals(rows, "", "").map((item) => item.id), [2, 1]);
});
test("reply drafts are separated by both account and conversation", () => {
  assert.notEqual(messageDraftKey(1, 7), messageDraftKey(2, 7));
  assert.notEqual(messageDraftKey(1, 7), messageDraftKey(1, 8));
  assert.equal(messageDraftKey(null, 7), null);
  assert.equal(messageDraftKey(1, null), null);
});
test("reply validation accepts multiline text and rejects empty and oversized messages", () => {
  assert.equal(validMessageBody("\n \t"), false);
  assert.equal(validMessageBody("Первая строка\nВторая строка"), true);
  assert.equal(validMessageBody("я".repeat(4000)), true);
  assert.equal(validMessageBody("я".repeat(4001)), false);
});

test("learning search and progress filters work together", () => {
  const rows = [{ id: 1, title: "Первая помощь", description: null, is_viewed: true },
    { id: 2, title: "Подготовка", description: "ПЕРВАЯ ПОМОЩЬ", is_viewed: false },
    { id: 3, title: "Тактика", description: null }];
  assert.deepEqual(filterMaterials(rows, " первая помощь ", "unread").map((item) => item.id), [2]);
  assert.deepEqual(filterMaterials(rows, "", "viewed").map((item) => item.id), [1]);
  assert.deepEqual(filterMaterials(rows, "", "unread").map((item) => item.id), [2, 3]);
});
test("learning progress suggests the first unstudied item and handles an empty course", () => {
  assert.deepEqual(learningProgress([{ id: 1, is_viewed: true }, { id: 2, is_viewed: false }]), { total: 2, completed: 1, percent: 50, nextId: 2 });
  assert.deepEqual(learningProgress([]), { total: 0, completed: 0, percent: 0, nextId: null });
  assert.deepEqual(learningProgress([{ id: 1, is_viewed: true }]), { total: 1, completed: 1, percent: 100, nextId: null });
});


test("calendar week starts on Monday in the club timezone", () => {
  const range = schedulePeriod("week", Date.parse("2026-10-11T18:00:00Z"), "Asia/Novosibirsk");
  assert.equal(range.from, "2026-10-12");
  assert.equal(range.to, "2026-10-19");
  assert.equal(eventInPeriod({ start_datetime: "2026-10-11T17:00:00Z" }, range, "Asia/Novosibirsk"), true);
  assert.equal(eventInPeriod({ start_datetime: "2026-10-18T17:00:00Z" }, range, "Asia/Novosibirsk"), false);
});
test("calendar month navigation crosses the year without rolling 31-day windows", () => {
  const range = schedulePeriod("month", Date.parse("2026-12-31T12:00:00Z"), "Asia/Novosibirsk", 1);
  assert.equal(range.from, "2027-01-01");
  assert.equal(range.to, "2027-02-01");
});
test("DST week still has seven calendar days", () => {
  const range = schedulePeriod("week", Date.parse("2026-03-29T12:00:00Z"), "Europe/Berlin");
  assert.equal(range.from, "2026-03-23");
  assert.equal(range.to, "2026-03-30");
});
