/* Shared global JS cached by browser */
(function () {
    function initCountdown() {
        var el = document.getElementById("countdown-seconds");
        if (!el || el.dataset.countdownInit === "1") {
            return;
        }
        el.dataset.countdownInit = "1";
        var startAttr = el.getAttribute("data-start");
        var remaining = parseInt(startAttr || el.textContent || "90", 10);
        if (isNaN(remaining) || remaining < 0) {
            remaining = 90;
        }
        function render() {
            if (remaining < 0) {
                remaining = 0;
            }
            el.textContent = String(remaining);
        }
        render();
        setInterval(function () {
            remaining -= 1;
            render();
        }, 1000);
    }

    function initDecisionValidation() {
        var form = document.getElementById("decision-form");
        if (!form || form.dataset.choiceValidateInit === "1") {
            return;
        }
        form.dataset.choiceValidateInit = "1";
        var errorEl = document.getElementById("choice-error");
        form.addEventListener("submit", function (e) {
            var checked = form.querySelector('input[name="choice"]:checked');
            if (!checked) {
                e.preventDefault();
                if (errorEl) {
                    errorEl.style.display = "block";
                }
            } else if (errorEl) {
                errorEl.style.display = "none";
            }
        });
    }

    function initPageEnhancements() {
        initCountdown();
        initDecisionValidation();
        initBatchWaitRefresh();
        initDelayedForm("delayedForm", 20000);
        initDelayedForm("delayedForm", 500);
        initExitQuestionnaireToggles();
        initInformedConsentValidation();
        initPathRedirect("BotDetection", "https://app.prolific.com/submissions/complete?cc=CXGNXKP6", 5000);
        initPathRedirect("FailedTest", "https://app.prolific.com/submissions/complete?cc=CK1M535Q", 10000);
        initPathRedirect("Thankyou", "https://app.prolific.com/submissions/complete?cc=COT13ZCM", 5000);
        initDelegatedDecisionAutosubmit();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initPageEnhancements);
    } else {
        initPageEnhancements();
    }

    function initBatchWaitRefresh() {
        if (window.location.pathname.indexOf("BatchWaitForGroup") === -1) {
            return;
        }
        // Don't force refresh when quit/wait choices are displayed.
        if (document.querySelector("a[href*='wait_more=1'],a[href*='quit=1']")) {
            return;
        }
        var refreshSeconds = 10 + Math.floor(Math.random() * 3);
        setTimeout(function () {
            window.location.reload();
        }, refreshSeconds * 1000);
    }

    function initDelayedForm(formId, delayMs) {
        var formEl = document.getElementById(formId);
        if (!formEl || formEl.dataset.delayInit === "1") {
            return;
        }
        formEl.dataset.delayInit = "1";
        setTimeout(function () {
            formEl.hidden = false;
        }, delayMs);
    }

    function initExitQuestionnaireToggles() {
        if (!document.querySelector("input[name='part_3_feedback']")) {
            return;
        }
        function setupToggle(radioName, otherContainerId, otherValue) {
            var radios = document.querySelectorAll('input[name="' + radioName + '"]');
            var otherBox = document.getElementById(otherContainerId);
            if (!radios.length || !otherBox) {
                return;
            }
            function toggleOther() {
                var selected = document.querySelector('input[name="' + radioName + '"]:checked');
                otherBox.style.display = selected && selected.value === otherValue ? "block" : "none";
            }
            radios.forEach(function (r) {
                r.addEventListener("change", toggleOther);
            });
            toggleOther();
        }
        setupToggle("part_3_feedback", "part3-other-container", "part_3_other");
        setupToggle("part_4_feedback", "part4-other-container", "part_4_other");
    }

    function initInformedConsentValidation() {
        var form = document.getElementById("consent-form");
        if (!form || form.dataset.validateInit === "1") {
            return;
        }
        form.dataset.validateInit = "1";
        form.addEventListener("submit", function (event) {
            var input = document.querySelector('input[name="prolific_id"]');
            var error = document.getElementById("error-msg");
            if (!input) {
                return;
            }
            var val = String(input.value || "").trim();
            var isValid = /^[A-Za-z0-9]{24}$/.test(val);
            if (!isValid) {
                event.preventDefault();
                if (error) {
                    error.style.display = "block";
                    error.textContent = "Please make sure that your Prolific ID is correct. You will not be able to proceed in the experiment without providing your Prolific ID.";
                }
            } else if (error) {
                error.style.display = "none";
            }
        });
    }

    function initPathRedirect(pathToken, url, delayMs) {
        if (window.location.pathname.indexOf(pathToken) === -1) {
            return;
        }
        setTimeout(function () {
            window.location.href = url;
        }, delayMs);
    }

    function initDelegatedDecisionAutosubmit() {
        if (window.location.pathname.indexOf("DelegatedDecision") === -1) {
            return;
        }
        var form = document.getElementById("auto-form");
        if (form) {
            form.submit();
        }
    }
})();
