import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

type Theme = "light" | "dark";
const storageKey = "beli-review-theme";
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");

function savedTheme(): Theme | null {
  try {
    const saved = localStorage.getItem(storageKey);
    return saved === "light" || saved === "dark" ? saved : null;
  } catch {
    return null;
  }
}

function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "dark" ? "#171f2c" : "#263853");
}

// Apply before React mounts, including while the saved data is loading.
applyTheme(savedTheme() ?? (systemTheme.matches ? "dark" : "light"));

export function ThemeToggle() {
  const [preference, setPreference] = useState<Theme | null>(savedTheme);
  const [systemDark, setSystemDark] = useState(systemTheme.matches);
  const theme = preference ?? (systemDark ? "dark" : "light");

  useEffect(() => {
    const updateSystem = (event: MediaQueryListEvent) =>
      setSystemDark(event.matches);
    const updateStorage = (event: StorageEvent) => {
      if (event.key === storageKey || event.key === null)
        setPreference(savedTheme());
    };
    systemTheme.addEventListener("change", updateSystem);
    window.addEventListener("storage", updateStorage);
    return () => {
      systemTheme.removeEventListener("change", updateSystem);
      window.removeEventListener("storage", updateStorage);
    };
  }, []);

  useEffect(() => applyTheme(theme), [theme]);

  function toggle() {
    const next = theme === "dark" ? "light" : "dark";
    setPreference(next);
    try {
      localStorage.setItem(storageKey, next);
    } catch {
      // Theme switching still works when browser storage is unavailable.
    }
  }

  return (
    <button
      type="button"
      className="icon-button theme-toggle"
      aria-label="Dark mode"
      aria-pressed={theme === "dark"}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      onClick={toggle}
    >
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
