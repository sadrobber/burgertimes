import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scrolls the window to the top on every path change, so a user tapping any
 * link (or landing on /menu from Home) sees the top of the new page rather
 * than the scroll position they had on the previous route.
 *
 * Renders nothing. Mount it inside <BrowserRouter> once, above <Routes>.
 */
export default function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    // instant, not smooth — feels snappier than a slow-motion scroll animation
    // and doesn't collide with existing page-load animations.
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
  }, [pathname]);
  return null;
}
