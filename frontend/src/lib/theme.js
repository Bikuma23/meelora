export const applyTheme = (theme) => {
  document.documentElement.classList.toggle("dark", theme === "dark");
};
