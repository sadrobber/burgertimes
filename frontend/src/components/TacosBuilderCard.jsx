import React from "react";
import { Sparkles } from "lucide-react";
import { useI18n } from "@/context/I18nContext.jsx";
import { builderImageUrl } from "@/lib/api";

// Stock fallback used only if no custom picture was uploaded from the admin
// (or if it ever 404s) — same "BT" halftone panel used elsewhere for menu
// items without a picture.
const FALLBACK_IMAGE_URL =
  "https://images.unsplash.com/photo-1565299585323-38d6b0865b47?w=1200&auto=format&fit=crop&q=80";

/**
 * A menu-item-shaped card for the Tacos Builder. Sits inline with the other
 * menu cards so the customer discovers it without an extra CTA banner.
 * Clicking anywhere on the card (or the Add button) opens the builder modal.
 * Tries the admin-uploaded picture first, falls back to a stock photo, then
 * to a plain "BT" placeholder if that ever fails too.
 */
export default function TacosBuilderCard({ onOpen }) {
  const { t } = useI18n();
  const [src, setSrc] = React.useState(builderImageUrl());
  const [imgOk, setImgOk] = React.useState(true);

  const handleError = () => {
    if (src !== FALLBACK_IMAGE_URL) setSrc(FALLBACK_IMAGE_URL);
    else setImgOk(false);
  };

  return (
    <div
      data-testid="menu-item-tacos-builder"
      onClick={onOpen}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      className="bt-card relative flex flex-col overflow-hidden cursor-pointer transition-transform hover:-translate-y-0.5 hover:border-[#EF2B2D] focus:outline-none focus:border-[#EF2B2D] group"
    >
      <div className="aspect-[4/3] w-full overflow-hidden bg-[#1A1A1A] relative">
        {imgOk ? (
          <img
            src={src}
            alt="Compose ton Tacos"
            loading="lazy"
            decoding="async"
            className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
            onError={handleError}
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bt-halftone">
            <div className="font-display text-4xl text-[#EF2B2D]/40 uppercase">BT</div>
          </div>
        )}
        <div className="absolute top-3 right-3">
          <span className="bt-price-pill">Sur mesure</span>
        </div>
        <div className="absolute top-3 left-3">
          <span className="bt-price-pill" style={{ background: "#EF2B2D", color: "#F5F1E8" }}>
            Nouveau
          </span>
        </div>
      </div>
      <div className="p-4 flex-1 flex flex-col">
        <div className="font-display text-2xl uppercase leading-none">Compose ton Tacos</div>
        <p className="text-sm text-[#B3B3B3] mt-2 line-clamp-2">
          Style, taille, viandes, suppléments, sauces. Fait comme tu l&apos;aimes.
        </p>
        <div className="mt-4">
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpen();
            }}
            data-testid="open-burger-builder"
            className="bt-btn-primary w-full"
          >
            <Sparkles className="w-4 h-4" /> {t("menu.build_burger")}
          </button>
        </div>
      </div>
    </div>
  );
}
