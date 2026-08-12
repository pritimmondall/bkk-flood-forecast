import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * LoginButton.jsx  (landing/)
 * ─────────────────────────────────────────────────────────────────────────────
 * Self-contained, production-ready login button component with two variants:
 *
 *  • "citizen" — warm gold/brass metallic treatment with golden glow on hover
 *  • "gov"     — cool blue/teal tone with matching neon glow on hover
 *
 * Both share: rounded rectangular shape, clean sans-serif typography,
 * box-shadow glow/bloom on hover, subtle scale + brightness lift,
 * smooth CSS transitions. All hover/glow states are CSS-driven.
 * ─────────────────────────────────────────────────────────────────────────────
 */

// ─── Types ────────────────────────────────────────────────────────────────────

// ─── Default labels ───────────────────────────────────────────────────────────

const DEFAULT_LABELS = {
  citizen: "Citizen Login",
  gov: "Gov Login"
};

// ─── Component ────────────────────────────────────────────────────────────────

/**
 * LoginButton — premium glow-effect login button.
 * Uses CSS classes `.login-btn-citizen` / `.login-btn-gov` defined in index.css
 * for hover glow, scale, and metallic gradient effects.
 */
export function LoginButton({
  variant,
  label,
  icon,
  ...buttonProps
}) {
  const displayLabel = label ?? DEFAULT_LABELS[variant];
  const variantClass = variant === "citizen" ? "login-btn-citizen" : "login-btn-gov";
  return /*#__PURE__*/_jsxs("button", {
    className: `login-btn ${variantClass}`,
    ...buttonProps,
    children: [icon && /*#__PURE__*/_jsx("span", {
      className: "login-btn-icon",
      children: icon
    }), /*#__PURE__*/_jsx("span", {
      children: displayLabel
    })]
  });
}