const tg = window.Telegram?.WebApp;

const roles = [
  { value: "PUBLIC_USER", title: "Гость", level: 0 },
  { value: "CANDIDATE", title: "Кандидат", level: 1 },
  { value: "USER_PENDING", title: "Ожидает привязки", level: 2 },
  { value: "PARTICIPANT", title: "Участник", level: 3 },
  { value: "DEPUTY_SQUAD_COMMANDER", title: "Зам. командира отделения", level: 4 },
  { value: "SQUAD_COMMANDER", title: "Командир отделения", level: 5 },
  { value: "DEPUTY_PLATOON_COMMANDER", title: "Зам. командира взвода", level: 6 },
  { value: "PLATOON_COMMANDER", title: "Командир взвода", level: 7 },
  { value: "ADMIN", title: "Администратор", level: 8 },
];

const roleButton = document.querySelector("#roleButton");
const grid = document.querySelector("#actionGrid");
const params = new URLSearchParams(window.location.search);
const initialRole = params.get("role");
const initialRoleIndex = roles.findIndex((role) => role.value === initialRole);
let roleIndex = initialRoleIndex >= 0 ? initialRoleIndex : 0;
const roleLocked = true;

const actions = [
  { key: "schedule", icon: "./assets/icons/schedule.png", title: "Расписание", hint: "занятия и опросы", min: 0 },
  { key: "my_squad", icon: "./assets/icons/my-squad.png", title: "Моё отделение", hint: "состав и контакты", min: 3 },
  { key: "full_roster", icon: "./assets/icons/full-roster.png", title: "Общий состав", hint: "все отделения", min: 3 },
  { key: "attendance", icon: "./assets/icons/attendance.png", title: "Посещаемость", hint: "мои отметки", min: 3 },
  { key: "norms", icon: "./assets/icons/norms.png", title: "Нормативы", hint: "сдать отчёт", min: 3 },
  { key: "notifications", icon: "./assets/icons/notifications.png", title: "Уведомления", hint: "важные сообщения", min: 3 },
  { key: "report", icon: "./assets/icons/report.png", title: "Проблема", hint: "написать командованию", min: 3, danger: true },
  { key: "announcements", icon: "./assets/icons/announcements.png", title: "Объявления", hint: "в своё отделение", min: 4 },
  { key: "mark_attendance", icon: "./assets/icons/mark-attendance.png", title: "Отметить явку", hint: "посещаемость", min: 4 },
  { key: "reports", icon: "./assets/icons/reports.png", title: "Отчёты", hint: "видео и нормативы", min: 5 },
  { key: "admin", icon: "./assets/icons/admin.png", title: "Админка", hint: "люди и права", min: 6 },
];

function render() {
  const role = roles[roleIndex];
  roleButton.textContent = role.title;
  roleButton.dataset.locked = roleLocked ? "true" : "false";
  grid.innerHTML = "";
  actions
    .filter((action) => action.min <= role.level)
    .forEach((action) => {
      const button = document.createElement("button");
      button.className = "tile";
      button.type = "button";
      button.dataset.danger = action.danger ? "true" : "false";
      button.dataset.staff = action.min > 0 ? "true" : "false";
      button.innerHTML = `
        <span class="tile-icon"><img src="${action.icon}" alt="" /></span>
        <span>
          <strong>${action.title}</strong>
          <span>${action.hint}</span>
        </span>
      `;
      button.addEventListener("click", () => {
        tg?.HapticFeedback?.impactOccurred("light");
        tg?.sendData(JSON.stringify({ key: action.key, title: action.title, role: role.value }));
      });
      grid.append(button);
    });
}

roleButton.addEventListener("click", () => {
  if (roleLocked) {
    return;
  }
  roleIndex = (roleIndex + 1) % roles.length;
  render();
});

tg?.ready();
tg?.expand();
render();
