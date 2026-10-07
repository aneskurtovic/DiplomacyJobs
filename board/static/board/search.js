// The job search form, kept out of inline htmx attributes so the Content-Security-Policy can forbid eval.
(() => {
  // A changed select searches at once; the text field has its own delayed trigger on the form.
  document.addEventListener("change", (event) => {
    if (event.target.tagName === "SELECT" && event.target.closest("#job-search")) htmx.trigger("#job-search", "filter-change");
  });
  // Empty fields stay out of the request and the pushed URL.
  document.addEventListener("htmx:configRequest", (event) => {
    if (event.detail.elt.id !== "job-search") return;
    for (const [name, value] of [...event.detail.formData]) if (!value) event.detail.formData.delete(name);
  });
})();
