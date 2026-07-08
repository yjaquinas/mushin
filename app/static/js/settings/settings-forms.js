(function () {
  "use strict";

  var accountForm = document.getElementById("settings-account-form");
  var passwordForm = document.getElementById("settings-password-form");

  function updateVisibilityExplanation(value) {
    var taglineEl = document.getElementById("visibility-tagline");
    var descEl = document.getElementById("visibility-description");
    if (!taglineEl || !descEl) return;
    var taglineSrc = document.getElementById("visibility-tagline-" + value);
    var descSrc = document.getElementById("visibility-desc-" + value);
    if (taglineSrc) taglineEl.textContent = taglineSrc.textContent;
    if (descSrc) descEl.textContent = descSrc.textContent;
  }

  // Account form: save button disabled by default, enable when privacy
  // selection or email value differs from the stored value.
  if (accountForm) {
    var submitBtn = accountForm.querySelector("[type=submit]");
    var radios = accountForm.querySelectorAll("[name=visibility]");
    var emailInput = document.getElementById("account-email");
    var originalVisibility = accountForm.getAttribute("data-original-visibility");
    var originalEmail = emailInput ? emailInput.getAttribute("data-original-value") || "" : "";

    function checkAccountForm() {
      if (!submitBtn) return;
      var checked = accountForm.querySelector("[name=visibility]:checked");
      var visChanged = checked && checked.value !== originalVisibility;
      var emailChanged = emailInput && emailInput.value !== originalEmail;
      submitBtn.disabled = !visChanged && !emailChanged;
    }

    if (submitBtn && originalVisibility) {
      submitBtn.disabled = true;
      updateVisibilityExplanation(originalVisibility);

      radios.forEach(function (radio) {
        radio.addEventListener("change", function () {
          if (radio.checked) updateVisibilityExplanation(radio.value);
          checkAccountForm();
        });
      });

      if (emailInput) {
        emailInput.addEventListener("input", checkAccountForm);
      }
    }
  }

  // Password: enable submit only when both fields are non-empty.
  if (passwordForm) {
    var currentPw = document.getElementById("account-current-password");
    var newPw = document.getElementById("account-new-password");
    var pwSubmit = passwordForm.querySelector("[type=submit]");
    if (currentPw && newPw && pwSubmit) {
      pwSubmit.disabled = true;
      function checkPasswordFields() {
        pwSubmit.disabled = !currentPw.value || !newPw.value;
      }
      currentPw.addEventListener("input", checkPasswordFields);
      newPw.addEventListener("input", checkPasswordFields);
    }
  }
})();
