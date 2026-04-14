if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {});
  });
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-question]");
  if (!button) {
    return;
  }

  const questionInput = document.querySelector("#id_question");
  if (!questionInput) {
    return;
  }

  questionInput.value = button.dataset.question;
  questionInput.focus();
});

const setFormBusy = (form) => {
  const submitButton =
    form.querySelector("[data-busy-submit]") ||
    form.querySelector("[data-indexing-submit]") ||
    form.querySelector("[type='submit']");
  const progress =
    form.querySelector("[data-busy-progress]") ||
    form.querySelector("[data-indexing-progress]") ||
    form.parentElement.querySelector("[data-busy-progress]") ||
    form.parentElement.querySelector("[data-indexing-progress]");
  const busyTarget = form.dataset.busyTarget ? document.querySelector(form.dataset.busyTarget) : null;
  const busyText = form.dataset.busyText || form.dataset.indexingBusyText || "진행 중입니다";

  if (submitButton) {
    submitButton.dataset.originalHtml = submitButton.innerHTML;
    submitButton.disabled = true;
    submitButton.innerHTML = `<span class="spinner-border spinner-border-sm me-2" aria-hidden="true"></span>${busyText}`;
  }

  if (progress) {
    progress.classList.remove("d-none");
  }

  if (busyTarget) {
    busyTarget.innerHTML = `
      <div class="busy-progress" role="status" aria-live="polite">
        <span class="spinner-border spinner-border-sm" aria-hidden="true"></span>
        <span>${busyText}. 잠시만 기다려 주세요.</span>
      </div>
    `;
  }
};

const resetFormBusy = (form) => {
  const submitButton =
    form.querySelector("[data-busy-submit]") ||
    form.querySelector("[data-indexing-submit]") ||
    form.querySelector("[type='submit']");
  const progress =
    form.querySelector("[data-busy-progress]") ||
    form.querySelector("[data-indexing-progress]") ||
    form.parentElement.querySelector("[data-busy-progress]") ||
    form.parentElement.querySelector("[data-indexing-progress]");

  if (submitButton && submitButton.dataset.originalHtml) {
    submitButton.disabled = false;
    submitButton.innerHTML = submitButton.dataset.originalHtml;
    delete submitButton.dataset.originalHtml;
  }

  if (progress) {
    progress.classList.add("d-none");
  }
};

document.addEventListener("submit", (event) => {
  const form = event.target.closest("[data-busy-form], [data-indexing-form]");
  if (!form) {
    return;
  }

  setFormBusy(form);
});

document.body.addEventListener("htmx:afterRequest", (event) => {
  const form = event.target.closest("[data-busy-form]");
  if (form) {
    resetFormBusy(form);
  }
});
