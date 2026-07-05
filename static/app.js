function evaluationForm() {
  return {
    counts: {},
    max: {},
    initLimits(limitJson) {
      this.max = limitJson || {};
    },
    recalc() {
      const counts = {};
      this.$root.querySelectorAll('input[type="radio"]:checked').forEach((item) => {
        const key = `${item.dataset.type}:${item.dataset.rule}:${item.value}`;
        counts[key] = (counts[key] || 0) + 1;
      });
      this.counts = counts;
    },
    isOverLimit(rule, option) {
      const key = `person:${rule}:${option}`;
      const limit = this.max[key];
      return limit !== undefined && (this.counts[key] || 0) > limit;
    },
    hasOverLimit() {
      return Object.keys(this.max).some((key) => (this.counts[key] || 0) > this.max[key]);
    }
  };
}

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-dialog-target]");
  if (trigger) {
    event.preventDefault();
    const dialog = document.getElementById(trigger.dataset.dialogTarget);
    if (dialog) dialog.showModal();
  }

  const closer = event.target.closest("[data-dialog-close]");
  if (closer) {
    const dialog = closer.closest("dialog");
    if (dialog) dialog.close();
  }
});

document.addEventListener("cancel", (event) => {
  if (event.target.matches("dialog")) {
    event.target.close();
  }
});

document.addEventListener("DOMContentLoaded", () => {
  const layout = document.querySelector(".layout");
  const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  if (layout && sidebarToggle) {
    const stored = window.localStorage.getItem("sidebarCollapsed");
    if (stored === "1") layout.classList.add("is-sidebar-collapsed");
    const syncLabel = () => {
      const collapsed = layout.classList.contains("is-sidebar-collapsed");
      sidebarToggle.setAttribute("aria-label", collapsed ? "展开菜单" : "折叠菜单");
      sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    };
    sidebarToggle.addEventListener("click", () => {
      layout.classList.toggle("is-sidebar-collapsed");
      window.localStorage.setItem("sidebarCollapsed", layout.classList.contains("is-sidebar-collapsed") ? "1" : "0");
      syncLabel();
    });
    syncLabel();
  }

  document.querySelectorAll("[data-person-rule-scope]").forEach((select) => {
    const sync = () => {
      const form = select.closest("form");
      const departments = form?.querySelector("[data-person-rule-departments]");
      if (departments) departments.classList.toggle("hidden", select.value === "same_department");
    };
    select.addEventListener("change", sync);
    sync();
  });

  document.querySelectorAll("[data-reviewer-position]").forEach((positionSelect) => {
    const form = positionSelect.closest("form");
    const userSelect = form?.querySelector("[data-reviewer-user]");
    if (!userSelect) return;

    const renderUsers = (users) => {
      const currentValue = userSelect.value;
      userSelect.innerHTML = "";
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "不指定，按评分人职位生成";
      userSelect.appendChild(empty);
      users.forEach((user) => {
        const option = document.createElement("option");
        option.value = String(user.id);
        option.textContent = user.name;
        userSelect.appendChild(option);
      });
      if ([...userSelect.options].some((option) => option.value === currentValue)) {
        userSelect.value = currentValue;
      }
    };

    const loadUsers = async () => {
      const positionId = positionSelect.value;
      if (!positionId) {
        renderUsers([]);
        return;
      }
      userSelect.disabled = true;
      try {
        const response = await fetch(`/admin/positions/${positionId}/reviewer-users`, { headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("Failed to load users");
        renderUsers(await response.json());
      } catch {
        renderUsers([]);
      } finally {
        userSelect.disabled = false;
      }
    };

    positionSelect.addEventListener("change", loadUsers);
  });

  document.querySelectorAll("[data-evaluation-form]").forEach((form) => {
    let limits = {};
    try {
      limits = JSON.parse(form.dataset.limits || "{}");
    } catch {
      limits = {};
    }
    const submit = form.querySelector("[data-submit-evaluation]");

    const recalc = () => {
      const counts = {};
      form.querySelectorAll('input[type="radio"]:checked').forEach((input) => {
        const key = `${input.dataset.type}:${input.dataset.rule}:${input.value}`;
        counts[key] = (counts[key] || 0) + 1;
      });
      form.querySelectorAll(".radio-option").forEach((label) => label.classList.remove("is-over-limit"));
      form.querySelectorAll("[data-task-row]").forEach((row) => {
        row.classList.toggle("is-complete", Boolean(row.querySelector('input[type="radio"]:checked')));
      });
      form.querySelectorAll(".task-section").forEach((section) => {
        const rows = Array.from(section.querySelectorAll("[data-task-row]"));
        const completed = rows.filter((row) => row.querySelector('input[type="radio"]:checked')).length;
        const progress = section.querySelector("[data-section-progress]");
        if (progress) progress.textContent = `${completed} / ${rows.length} 已评`;
      });
      const rows = Array.from(form.querySelectorAll("[data-task-row]"));
      const completed = rows.filter((row) => row.querySelector('input[type="radio"]:checked')).length;
      document.querySelectorAll("[data-progress-text]").forEach((item) => {
        item.textContent = `已完成 ${completed} / ${rows.length}`;
      });
      Object.entries(limits).forEach(([key, max]) => {
        if ((counts[key] || 0) > max) {
          const [type, rule, option] = key.split(":");
          form.querySelectorAll(`input[data-type="${type}"][data-rule="${rule}"][value="${option}"]:checked`).forEach((input) => {
            input.closest(".radio-option")?.classList.add("is-over-limit");
          });
        }
      });
      if (submit) submit.disabled = rows.length === 0 || completed < rows.length;
    };

    form.querySelectorAll("[data-quick-fill-option]").forEach((button) => {
      button.addEventListener("click", () => {
        const section = button.closest(".task-section");
        if (!section) return;
        const rows = Array.from(section.querySelectorAll("[data-task-row]"));
        const optionId = button.dataset.quickFillOption;

        rows.forEach((row) => {
          const input = row.querySelector(`input[type="radio"][value="${optionId}"]`);
          if (input) input.checked = true;
        });
        recalc();
      });
    });

    form.addEventListener("change", recalc);
    recalc();
  });

  document.querySelectorAll(".checkbox-list").forEach((list) => {
    const checkboxes = Array.from(list.querySelectorAll('input[type="checkbox"][name="target_department_ids"][data-department-id]'));
    const rows = Array.from(list.querySelectorAll("[data-department-row]"));
    const rowById = rows.reduce((result, row) => {
      result[row.dataset.departmentId] = row;
      return result;
    }, {});
    const rowsByParent = rows.reduce((result, row) => {
      const parentId = row.dataset.parentId;
      if (!parentId) return result;
      if (!result[parentId]) result[parentId] = [];
      result[parentId].push(row);
      return result;
    }, {});
    const collapsedIds = new Set();

    const setDescendants = (departmentId, checked) => {
      const children = rowsByParent[departmentId] || [];
      children.forEach((row) => {
        const checkbox = row.querySelector('input[type="checkbox"][name="target_department_ids"]');
        if (checkbox) checkbox.checked = checked;
        setDescendants(row.dataset.departmentId, checked);
      });
    };

    const descendantCheckboxes = (departmentId) => {
      const result = [];
      const collect = (id) => {
        (rowsByParent[id] || []).forEach((row) => {
          const checkbox = row.querySelector('input[type="checkbox"][name="target_department_ids"]');
          if (checkbox) result.push(checkbox);
          collect(row.dataset.departmentId);
        });
      };
      collect(departmentId);
      return result;
    };

    const hasCollapsedAncestor = (row) => {
      let parentId = row.dataset.parentId;
      while (parentId) {
        if (collapsedIds.has(parentId)) return true;
        parentId = rowById[parentId]?.dataset.parentId || "";
      }
      return false;
    };

    const syncTree = () => {
      rows.forEach((row) => {
        row.classList.toggle("hidden", hasCollapsedAncestor(row));
      });
      list.querySelectorAll("[data-select-descendants]").forEach((button) => {
        const row = button.closest("[data-department-row]");
        const descendants = row ? descendantCheckboxes(row.dataset.departmentId) : [];
        const allChecked = descendants.length > 0 && descendants.every((item) => item.checked);
        button.textContent = allChecked ? "清下级" : "选下级";
        button.setAttribute("aria-label", `${allChecked ? "取消选择" : "选择"}${row?.textContent.trim() || ""}的下级部门`);
      });
    };

    const toggleRow = (row) => {
      if (!row) return;
      const id = row.dataset.departmentId;
      const collapsed = !collapsedIds.has(id);
      if (collapsed) {
        collapsedIds.add(id);
      } else {
        collapsedIds.delete(id);
      }
      const button = row.querySelector("[data-tree-toggle]");
      if (button) {
        button.classList.toggle("is-collapsed", collapsed);
        button.textContent = collapsed ? "+" : "-";
        button.setAttribute("aria-expanded", String(!collapsed));
        button.setAttribute("aria-label", `${collapsed ? "展开" : "收起"}${row.textContent.trim()}`);
      }
      syncTree();
    };

    list.querySelectorAll("[data-tree-toggle], [data-tree-toggle-label]").forEach((control) => {
      const row = control.closest("[data-department-row]");
      control.addEventListener("click", () => toggleRow(row));
    });

    list.querySelectorAll("[data-select-descendants]").forEach((button) => {
      const row = button.closest("[data-department-row]");
      button.addEventListener("click", () => {
        if (!row) return;
        const descendants = descendantCheckboxes(row.dataset.departmentId);
        const allChecked = descendants.length > 0 && descendants.every((item) => item.checked);
        setDescendants(row.dataset.departmentId, !allChecked);
        syncTree();
      });
    });

    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", syncTree));
    syncTree();
  });
});
