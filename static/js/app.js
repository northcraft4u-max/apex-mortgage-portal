document.addEventListener("DOMContentLoaded", () => {
  const loaderBar = document.getElementById("spaLoaderBar");

  function initInteractiveWidgets() {
    // 1. Scroll Reveal Observer
    const observer = new IntersectionObserver((entries, obs) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("visible");
          obs.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });

    document.querySelectorAll(".reveal").forEach((el) => observer.observe(el));

    // 2. Animated KPI Counters (Home Page)
    document.querySelectorAll(".counter").forEach((counter) => {
      if (counter.dataset.animated) return;
      counter.dataset.animated = "true";
      const target = +counter.getAttribute("data-target");
      const suffix = counter.getAttribute("data-suffix") || "";
      let current = 0;
      const step = target / 45;
      const timer = setInterval(() => {
        current += step;
        if (current >= target) {
          counter.textContent = target + suffix;
          clearInterval(timer);
        } else {
          counter.textContent = Math.floor(current) + suffix;
        }
      }, 20);
    });
  }

  function updateActiveNav(pathname) {
    document.querySelectorAll(".nav-pill").forEach((link) => {
      const linkUrl = new URL(link.href, window.location.origin);
      if (linkUrl.pathname === pathname) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });
  }

  // React-like instant SPA page swap for internal GET links
  async function navigateSpa(url, pushHistory = true) {
    const mainEl = document.querySelector("main");
    if (!mainEl) {
      window.location.href = url;
      return;
    }

    try {
      if (loaderBar) {
        loaderBar.style.opacity = "1";
        loaderBar.style.width = "65%";
      }
      mainEl.classList.add("spa-leaving");

      const response = await fetch(url, { headers: { "X-Requested-With": "SPA" } });
      const htmlText = await response.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(htmlText, "text/html");
      const nextMain = doc.querySelector("main");

      if (!nextMain) {
        window.location.href = url;
        return;
      }

      setTimeout(() => {
        document.title = doc.title;
        mainEl.innerHTML = nextMain.innerHTML;

        // Re-execute page-specific inline scripts inside swapped <main>
        mainEl.querySelectorAll("script").forEach((oldScript) => {
          const newScript = document.createElement("script");
          newScript.textContent = oldScript.textContent;
          oldScript.replaceWith(newScript);
        });

        if (pushHistory) {
          window.history.pushState({}, "", url);
        }
        const parsedUrl = new URL(url, window.location.origin);
        updateActiveNav(parsedUrl.pathname);

        // Collapse mobile navbar if open
        const navCollapse = document.getElementById("mainNav");
        if (navCollapse && navCollapse.classList.contains("show")) {
          bootstrap.Collapse.getOrCreateInstance(navCollapse).hide();
        }

        window.scrollTo({ top: 0, behavior: "instant" });
        mainEl.classList.remove("spa-leaving");
        initInteractiveWidgets();

        if (loaderBar) {
          loaderBar.style.width = "100%";
          setTimeout(() => {
            loaderBar.style.opacity = "0";
            loaderBar.style.width = "0%";
          }, 180);
        }
      }, 140);
    } catch (err) {
      window.location.href = url;
    }
  }

  document.addEventListener("click", (e) => {
    const link = e.target.closest("a[data-spa]");
    if (!link) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    if (link.href !== window.location.href) {
      navigateSpa(link.href, true);
    }
  });

  window.addEventListener("popstate", () => {
    navigateSpa(window.location.href, false);
  });

  initInteractiveWidgets();
});