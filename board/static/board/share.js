// "Share" on a job page: the phone's share sheet where there is one, otherwise the link is copied.
(() => {
  const box = document.querySelector(".share");
  if (!box) return;
  const button = box.querySelector("button");
  const status = box.querySelector(".share-status");
  const url = document.querySelector('link[rel="canonical"]')?.href || location.href;
  box.hidden = false;
  button.addEventListener("click", async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: button.dataset.shareTitle, url });
      } catch (error) {
        // Closing the share sheet is not an error worth showing.
      }
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      status.textContent = button.dataset.copied;
    } catch (error) {
      status.textContent = button.dataset.failed;
    }
  });
})();
