"use client";

import React, { useState } from "react";
import { cn } from "@/lib/utils";

export interface GenerateButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  /**
   * The hue value (0-360) for the button's highlight color.
   * Default is 195 (Cyan/Blue).
   */
  hue?: number;
  /**
   * If true, forces the button into its "Generating" state.
   */
  isGenerating?: boolean;
  /**
   * Primary label text (defaults to "Extract & Align Topics")
   */
  label?: string;
  /**
   * Label shown while generating (defaults to "Extracting & Aligning...")
   */
  generatingLabel?: string;
}

export function GenerateButton({
  hue = 195,
  isGenerating = false,
  label = "Extract & Align Topics",
  generatingLabel = "Extracting & Aligning...",
  className,
  onClick,
  disabled,
  ...props
}: GenerateButtonProps) {
  return (
    <div className="relative inline-block group">
      <style>{`
        .gen-btn {
          --border-radius: 9999px;
          --transition: 0.25s ease;
          --button-gradient: linear-gradient(90deg, #4f46e5 0%, #2563eb 50%, #059669 100%);
          --highlight-color-hue: ${hue}deg;

          position: relative;
          isolation: isolate;
          user-select: none;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          padding: 0.65rem 1.35rem;
          font-family: inherit;
          font-size: 0.875rem;
          line-height: 1.25rem;
          font-weight: 600;
          letter-spacing: -0.01em;
          color: #ffffff;
          -webkit-font-smoothing: antialiased;
          -moz-osx-font-smoothing: grayscale;

          background-image: var(--button-gradient);

          box-shadow:
            inset 0px 1px 0px rgba(255, 255, 255, 0.35),
            0px 4px 12px -2px rgba(37, 99, 235, 0.35),
            0px 2px 6px -1px rgba(5, 150, 105, 0.25);

          border: 1px solid rgba(255, 255, 255, 0.22);
          border-radius: var(--border-radius);
          cursor: pointer;

          transition: transform var(--transition), box-shadow var(--transition), filter var(--transition), opacity var(--transition);
        }

        .gen-btn:disabled {
          opacity: 0.55;
          cursor: not-allowed;
          box-shadow: none;
        }

        .gen-btn:not(:disabled):hover {
          transform: translateY(-1px);
          filter: brightness(1.06);
          box-shadow:
            inset 0px 1px 0px rgba(255, 255, 255, 0.45),
            0px 8px 20px -4px rgba(37, 99, 235, 0.45),
            0px 4px 10px -2px rgba(5, 150, 105, 0.35);
        }

        .gen-btn:not(:disabled):active {
          transform: translateY(0px);
          filter: brightness(0.98);
        }

        .gen-btn-svg {
          position: relative;
          z-index: 2;
          flex-shrink: 0;
          height: 18px;
          width: 18px;
          fill: #ffffff;
          transition: transform 0.3s ease;
        }

        .gen-btn:not(:disabled):hover .gen-btn-svg {
          transform: scale(1.1) rotate(6deg);
        }

        .gen-btn[data-generating="true"] .gen-btn-svg {
          animation: gen-spin-pulse 1.4s ease-in-out infinite;
        }

        @keyframes gen-spin-pulse {
          0%, 100% { transform: scale(1) rotate(0deg); opacity: 1; }
          50% { transform: scale(1.18) rotate(15deg); opacity: 0.85; }
        }

        .gen-txt-wrapper {
          position: relative;
          z-index: 2;
          display: inline-flex;
          align-items: center;
          white-space: nowrap;
          color: #ffffff;
        }
      `}</style>

      <button
        type="button"
        disabled={disabled}
        className={cn("gen-btn", className)}
        data-generating={isGenerating}
        onClick={(e) => {
          if (disabled) return;
          onClick?.(e);
        }}
        {...props}
      >
        <svg className="gen-btn-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M9.813 15.904 9 18.75l-.813-2.846a4.5 4.5 0 0 0-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 0 0 3.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 0 0 3.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 0 0-3.09 3.09ZM18.259 8.715 18 9.75l-.259-1.035a3.375 3.375 0 0 0-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 0 0 2.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 0 0 2.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 0 0-2.456 2.456ZM16.894 20.567 16.5 21.75l-.394-1.183a2.25 2.25 0 0 0-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 0 0 1.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 0 0 1.423 1.423l1.183.394-1.183.394a2.25 2.25 0 0 0-1.423 1.423Z"
          />
        </svg>

        <span className="gen-txt-wrapper">
          {isGenerating ? generatingLabel : label}
        </span>
      </button>
    </div>
  );
}

export default GenerateButton;
