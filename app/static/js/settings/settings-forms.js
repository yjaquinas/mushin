(function () {
  "use strict";

  function updateVisibilityExplanation(value) {
    var taglineEl = document.getElementById("settings-text-visibility-tagline");
    var descEl = document.getElementById("settings-text-visibility-description");
    if (!taglineEl || !descEl) return;
    var taglineSrc = document.getElementById("settings-text-visibility-tagline-" + value);
    var descSrc = document.getElementById("settings-text-visibility-desc-" + value);
    if (taglineSrc) taglineEl.textContent = taglineSrc.textContent;
    if (descSrc) descEl.textContent = descSrc.textContent;
  }

  function initAccountForm() {
    var accountForm = document.getElementById("settings-form-account");
    if (!accountForm || accountForm.settingsInit) return;
    accountForm.settingsInit = true;
    accountForm.removeAttribute("data-settings-init");

    var submitBtn = accountForm.querySelector("[type=submit]");
    var emailInput = document.getElementById("settings-field-email");
    var originalVisibility = accountForm.getAttribute("data-original-visibility");
    var originalEmail = emailInput ? emailInput.getAttribute("data-original-value") || "" : "";

    function checkAccountForm() {
      if (!submitBtn) return;
      var checked = accountForm.querySelector("[name=visibility]:checked");
      var visChanged = checked && checked.value !== originalVisibility;
      var emailChanged = emailInput && emailInput.value !== originalEmail;
      submitBtn.disabled = !visChanged && !emailChanged;
    }

    if (!submitBtn || !originalVisibility) return;
    submitBtn.disabled = true;
    updateVisibilityExplanation(originalVisibility);

    accountForm.addEventListener("change", function (event) {
      if (event.target && event.target.name === "visibility") {
        updateVisibilityExplanation(event.target.value);
      }
      checkAccountForm();
    });
    accountForm.addEventListener("input", checkAccountForm);
    checkAccountForm();
  }

  function initPasswordForm() {
    var passwordForm = document.getElementById("settings-form-password");
    if (!passwordForm || passwordForm.settingsInit) return;
    passwordForm.settingsInit = true;
    passwordForm.removeAttribute("data-settings-init");

    var currentPw = document.getElementById("settings-field-current-password");
    var newPw = document.getElementById("settings-field-new-password");
    var submitBtn = passwordForm.querySelector("[type=submit]");
    if (!currentPw || !newPw || !submitBtn) return;

    submitBtn.disabled = true;
    function checkPasswordFields() {
      submitBtn.disabled = !currentPw.value || !newPw.value;
    }
    currentPw.addEventListener("input", checkPasswordFields);
    newPw.addEventListener("input", checkPasswordFields);
  }

  function initSettingsForms() {
    initAccountForm();
    initPasswordForm();
  }

  document.addEventListener("DOMContentLoaded", initSettingsForms);
  document.body.addEventListener("htmx:afterSwap", initSettingsForms);
  document.body.addEventListener("tab:panel-rendered", initSettingsForms);
})();
