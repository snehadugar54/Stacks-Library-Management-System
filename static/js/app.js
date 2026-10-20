const $ = (selector) => document.querySelector(selector);
const role = document.body.dataset.role;
const api = async (url, options = {}) => {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.text();
  let data;
  try {
    data = body ? JSON.parse(body) : {};
  } catch {
    const status = `${response.status}${response.statusText ? ` ${response.statusText}` : ""}`;
    if (!response.ok)
      throw new Error(`Request failed (${status}); the server returned a non-JSON response.`);
    throw new Error("The server returned an invalid response.");
  }
  if (!response.ok)
    throw new Error(data.error || data.message || `Request failed with status ${response.status}.`);
  return data;
};
const dateLabel = (value) =>
  new Date(`${value}T00:00:00`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
const dateTimeLabel = (value) =>
  new Date(value).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
let toastTimer;
function toast(message) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.remove("show"), 3400);
}
function openModal(id) {
  if (id === "issue-modal") loadIssueOptions();
  $(`#${id}`).showModal();
}
function bookRow(book) {
  const low = book.available_copies < 1;
  return `<tr><td class="table-title">${book.title}</td><td>${book.author}</td><td>${book.category}</td><td>${book.isbn}</td><td><span class="badge ${low ? "low" : "available"}">${book.available_copies} of ${book.total_copies} available</span></td></tr>`;
}
async function loadDashboard() {
  const data = await api("/api/dashboard");
  const labels = [
    ["Titles", data.stats.titles],
    ["Available copies", data.stats.available],
    ["Registered members", data.stats.members],
    ["Active loans", data.stats.active_loans],
    ["Overdue", data.stats.overdue],
    ["Pending fines", `₹${data.stats.pending_fines.toFixed(2)}`],
  ];
  $("#stats").innerHTML = labels
    .map(
      ([label, value]) =>
        `<div class="stat"><p>${label}</p><strong>${value}</strong></div>`,
    )
    .join("");
  $("#recent-loans").innerHTML = data.recent.length
    ? data.recent
        .map(
          (loan) =>
            `<tr><td class="table-title">${loan.title}</td><td>${loan.member}</td><td>${dateLabel(loan.issued_on)}</td><td>${dateLabel(loan.due_on)}</td><td><span class="badge ${new Date(loan.due_on) < new Date() ? "overdue" : "available"}">${new Date(loan.due_on) < new Date() ? "Overdue" : "Active"}</span></td></tr>`,
        )
        .join("")
    : '<tr><td colspan="5">No active loans.</td></tr>';
}
async function loadBooks(query = "") {
  const books = await api(`/api/books?q=${encodeURIComponent(query)}`);
  $("#books-table").innerHTML =
    books.map(bookRow).join("") ||
    '<tr><td colspan="5">No books found.</td></tr>';
  $("#book-count").textContent =
    `${books.length} title${books.length === 1 ? "" : "s"}`;
  return books;
}
async function loadMembers() {
  const members = await api("/api/members");
  $("#members-table").innerHTML =
    members
      .map(
        (member) =>
          `<tr><td class="table-title">${escapeHtml(member.name)}</td><td>${escapeHtml(member.email)}</td><td>${escapeHtml(member.phone || "—")}</td><td>${dateLabel(member.joined_on)}</td><td><button class="button secondary delete-member" data-id="${Number(member.id)}" data-name="${escapeHtml(member.name)}" data-email="${escapeHtml(member.email)}">Delete</button></td></tr>`,
      )
      .join("") || '<tr><td colspan="5">No members registered.</td></tr>';
  return members;
}
async function loadLoans() {
  const loans = await api("/api/loans");
  $("#loans-table").innerHTML =
    loans
      .map((loan) => {
        const status = loan.returned_on
          ? '<span class="badge returned">Returned</span>'
          : loan.overdue_days
            ? `<span class="badge overdue">${loan.overdue_days} days overdue</span>`
            : '<span class="badge available">Active</span>';
        const fine = loan.fine
          ? `₹${loan.fine.toFixed(2)} ${loan.paid ? '<span class="badge returned">Paid</span>' : ""}`
          : "—";
        const action = !loan.returned_on
          ? `<button class="button secondary return-loan" data-id="${loan.id}">Return</button>`
          : !loan.paid && loan.fine
            ? `<button class="button secondary pay-fine" data-id="${loan.id}">Mark paid</button>`
            : "—";
        return `<tr><td><span class="table-title">${loan.title}</span><span class="table-sub">${loan.member}</span></td><td>${dateLabel(loan.issued_on)}</td><td>${dateLabel(loan.due_on)}</td><td>${status}</td><td>${fine}</td><td>${action}</td></tr>`;
      })
      .join("") || '<tr><td colspan="6">No lending records.</td></tr>';
}
async function loadAutomationLogs() {
  const logs = await api("/api/automation/logs");
  $("#automation-logs-table").innerHTML =
    logs
      .map((log) => {
        const emailBadge = log.message && log.message.includes("[Email: SENT]")
          ? ' <span class="badge available">Email sent</span>'
          : log.message && log.message.includes("[Email: FAILED]")
            ? ' <span class="badge overdue">Email failed</span>'
            : "";
        return `<tr><td><span class="table-title">${escapeHtml(log.member_name)}</span><span class="table-sub">${escapeHtml(log.member_email)}</span></td><td>${escapeHtml(log.book_title)}</td><td>${dateLabel(log.due_on)}</td><td>${log.overdue_days}</td><td>₹${Number(log.fine).toFixed(2)}</td><td><span class="badge ${log.status === "SUCCESS" ? "available" : "overdue"}">${escapeHtml(log.status)}</span>${emailBadge}</td><td>${dateTimeLabel(log.run_at)}</td></tr>`;
      })
      .join("") || '<tr><td colspan="7">No automation runs have been logged yet.</td></tr>';
  return logs;
}
async function loadActivityLogs() {
  const logs = await api("/api/activity-logs");
  const table = $("#activity-log-table");
  if (!table) return logs;
  table.innerHTML =
    logs
      .map(
        (log) =>
          `<tr><td><span class="table-title">${escapeHtml(log.user_name)}</span></td><td><span class="badge ${log.user_role === "admin" ? "low" : "available"}">${escapeHtml(log.user_role.toUpperCase())}</span></td><td><span class="table-title">${escapeHtml(log.action)}</span></td><td>${escapeHtml(log.details || "—")}</td><td>${dateTimeLabel(log.timestamp)}</td></tr>`,
      )
      .join("") || '<tr><td colspan="5">No user activity recorded yet.</td></tr>';
  return logs;
}
async function loadIssueOptions() {
  const [books, members] = await Promise.all([
    api("/api/books"),
    api("/api/members"),
  ]);
  const available = books.filter((book) => book.available_copies > 0);
  $("#issue-books").innerHTML =
    available
      .map(
        (book) =>
          `<option value="${book.id}">${book.title} (${book.available_copies} available)</option>`,
      )
      .join("") || '<option value="">No books available</option>';
  $("#issue-members").innerHTML =
    members
      .map(
        (member) =>
          `<option value="${member.id}">${member.name} — ${member.email}</option>`,
      )
      .join("") || '<option value="">No members registered</option>';
}
async function refresh() {
  const tasks = [
    loadDashboard(),
    loadBooks($("#book-search").value),
    loadLoans(),
  ];
  if ($("#members-table")) tasks.push(loadMembers());
  await Promise.all(tasks);
}
document.querySelectorAll("[data-view]").forEach((link) =>
  link.addEventListener("click", (event) => {
    event.preventDefault();
    const view = link.dataset.view;
    document
      .querySelectorAll(".view")
      .forEach((item) => item.classList.toggle("active", item.id === view));
    document
      .querySelectorAll(".nav-link")
      .forEach((item) =>
        item.classList.toggle("active", item.dataset.view === view),
      );
    $("#page-title").textContent = {
      dashboard: "Good morning, Admin",
      books: "Book catalogue",
      members: "Member directory",
      loans: "Issue & returns",
      "activity-log": "User activity history",
      automation: "Automation centre",
      "automation-logs": "Automation log",
    }[view];
    if (view === "automation-logs") loadAutomationLogs().catch((error) => toast(error.message));
    if (view === "activity-log") loadActivityLogs().catch((error) => toast(error.message));
    location.hash = view;
  }),
);
document
  .querySelectorAll("[data-open]")
  .forEach((button) =>
    button.addEventListener("click", () => openModal(button.dataset.open)),
  );
document
  .querySelectorAll("[data-close]")
  .forEach((button) =>
    button.addEventListener("click", () => button.closest("dialog").close()),
  );
if ($("#book-form"))
  $("#book-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const form = Object.fromEntries(new FormData(event.target));
      await api("/api/books", { method: "POST", body: JSON.stringify(form) });
      event.target.reset();
      event.target.closest("dialog").close();
      toast("Book added to the catalogue.");
      refresh();
    } catch (error) {
      toast(error.message);
    }
  });
if ($("#member-form"))
  $("#member-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/members", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(event.target))),
      });
      event.target.reset();
      event.target.closest("dialog").close();
      toast("Member registered.");
      refresh();
    } catch (error) {
      toast(error.message);
    }
  });
if ($("#members-table"))
  $("#members-table").addEventListener("click", async (event) => {
    const button = event.target.closest(".delete-member");
    if (!button) return;

    const { id, name, email } = button.dataset;
    if (!window.confirm(`Delete ${name} (${email})? This cannot be undone.`)) return;

    try {
      const result = await api(`/api/members/${encodeURIComponent(id)}`, {
        method: "DELETE",
      });
      await loadMembers();
      toast(result.message);
    } catch (error) {
      toast(error.message);
    }
  });
if ($("#issue-form"))
  $("#issue-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const data = Object.fromEntries(new FormData(event.target));
      await api("/api/loans", { method: "POST", body: JSON.stringify(data) });
      event.target.closest("dialog").close();
      toast("Book issued successfully.");
      refresh();
    } catch (error) {
      toast(error.message);
    }
  });
$("#loans-table").addEventListener("click", async (event) => {
  const id = event.target.dataset.id;
  if (!id) return;
  try {
    const endpoint = event.target.classList.contains("return-loan")
      ? `/api/loans/${id}/return`
      : `/api/loans/${id}/pay`;
    const result = await api(endpoint, { method: "POST" });
    toast(result.message);
    refresh();
  } catch (error) {
    toast(error.message);
  }
});
if ($("#run-overdue"))
  $("#run-overdue").addEventListener("click", async () => {
    const button = $("#run-overdue");
    const status = $("#automation-status");
    button.disabled = true;
    button.textContent = "Running overdue check…";
    status.textContent = "The overdue reminder bot is running.";
    try {
      const result = await api("/api/automation/overdue/run-bot", { method: "POST" });
      status.textContent = "Overdue reminder bot completed successfully. View the automation log for details.";
      toast(result.message);
      loadAutomationLogs().catch((error) => toast(error.message));
    } catch (error) {
      status.textContent = `Overdue reminder bot failed: ${error.message}`;
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Run overdue check";
    }
  });
if ($("#run-courtesy"))
  $("#run-courtesy").addEventListener("click", async () => {
    const button = $("#run-courtesy");
    const status = $("#courtesy-status");
    button.disabled = true;
    button.textContent = "Running courtesy check…";
    status.textContent = "The courtesy reminder bot is running.";
    try {
      const result = await api("/api/automation/courtesy", { method: "POST" });
      status.textContent = result.message;
      toast(result.message);
      loadAutomationLogs().catch((error) => toast(error.message));
    } catch (error) {
      status.textContent = `Courtesy reminder failed: ${error.message}`;
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Run courtesy check";
    }
  });
if ($("#run-inventory-audit"))
  $("#run-inventory-audit").addEventListener("click", async () => {
    const button = $("#run-inventory-audit");
    const status = $("#inventory-audit-status");
    button.disabled = true;
    button.textContent = "Running audit…";
    status.textContent = "Inventory audit is running.";
    try {
      const result = await api("/api/automation/inventory-audit", { method: "POST" });
      status.textContent = `Audited ${result.total_titles} titles: ${result.depleted_titles} depleted, ${result.low_stock_titles} low stock.`;
      toast(result.message);
    } catch (error) {
      status.textContent = `Inventory audit failed: ${error.message}`;
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Run inventory audit";
    }
  });
if ($("#run-daily-reconciliation"))
  $("#run-daily-reconciliation").addEventListener("click", async () => {
    const button = $("#run-daily-reconciliation");
    const status = $("#daily-reconciliation-status");
    button.disabled = true;
    button.textContent = "Running reconciliation…";
    status.textContent = "Compiling daily managerial digest and financial summary…";
    try {
      const result = await api("/api/automation/daily-reconciliation", { method: "POST" });
      status.textContent = `Reconciliation complete. Issued: ${result.summary.books_issued_today}, Returned: ${result.summary.books_returned_today}, Overdue: ${result.summary.active_overdue_count}. [Email: ${result.email_status}]`;
      toast(result.message);
    } catch (error) {
      status.textContent = `Reconciliation failed: ${error.message}`;
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Run daily digest";
    }
  });
if ($("#run-member-invitations"))
  $("#run-member-invitations").addEventListener("click", async () => {
    const button = $("#run-member-invitations");
    const status = $("#member-invitations-status");
    button.disabled = true;
    button.textContent = "Sending invitations…";
    status.textContent = "Scanning unactivated members and dispatching invitations…";
    try {
      const result = await api("/api/automation/member-invitations", { method: "POST" });
      status.textContent = `Processed ${result.processed} unactivated member(s). Sent: ${result.emails_sent} invitation email(s).`;
      toast(result.message);
    } catch (error) {
      status.textContent = `Member invitation failed: ${error.message}`;
      toast(error.message);
    } finally {
      button.disabled = false;
      button.textContent = "Send invitations";
    }
  });
if ($("#select-catalogue-csv") && $("#catalogue-csv-input")) {
  const fileInput = $("#catalogue-csv-input");
  const selectBtn = $("#select-catalogue-csv");
  const uploadBtn = $("#upload-catalogue-csv");
  const csvStatus = $("#catalogue-csv-status");

  selectBtn.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (file) {
      selectBtn.textContent = file.name.length > 20 ? file.name.substring(0, 17) + "…" : file.name;
      uploadBtn.disabled = false;
      csvStatus.textContent = `Selected "${file.name}" (${file.size} bytes). Ready to ingest.`;
    } else {
      selectBtn.textContent = "Select CSV";
      uploadBtn.disabled = true;
      csvStatus.textContent = "Ready to ingest catalogue CSV.";
    }
  });

  if (uploadBtn) {
    uploadBtn.addEventListener("click", async () => {
      const file = fileInput.files[0];
      if (!file) return toast("Please select a CSV file first.");

      uploadBtn.disabled = true;
      uploadBtn.textContent = "Ingesting…";
      csvStatus.textContent = "Parsing CSV and loading books into catalogue…";

      try {
        const text = await file.text();
        const result = await api("/api/automation/books/import-csv", {
          method: "POST",
          body: JSON.stringify({ csv_data: text }),
        });
        csvStatus.textContent = `Ingestion complete: ${result.inserted_count} added, ${result.updated_count} updated, ${result.skipped_count} skipped.`;
        toast(result.message);
        fileInput.value = "";
        selectBtn.textContent = "Select CSV";
        uploadBtn.disabled = true;
        loadBooks().catch(() => {});
        loadDashboard().catch(() => {});
        loadActivityLogs().catch(() => {});
      } catch (error) {
        csvStatus.textContent = `Ingestion failed: ${error.message}`;
        toast(error.message);
        uploadBtn.disabled = false;
      } finally {
        uploadBtn.textContent = "Ingest CSV";
      }
    });
  }
}
if ($("#refresh-automation-logs"))
  $("#refresh-automation-logs").addEventListener("click", () =>
    loadAutomationLogs()
      .then(() => toast("Automation log refreshed."))
      .catch((error) => toast(error.message)),
  );
if ($("#refresh-activity-log"))
  $("#refresh-activity-log").addEventListener("click", () =>
    loadActivityLogs()
      .then(() => toast("Activity history refreshed."))
      .catch((error) => toast(error.message)),
  );
$("#book-search").addEventListener("input", (event) =>
  loadBooks(event.target.value),
);
$("#today").textContent = new Date()
  .toLocaleDateString("en-IN", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  })
  .toUpperCase();
refresh().catch((error) => toast(error.message));
