/**
 * English messages. The source dictionary: its shape defines the `Messages` type, so the
 * Somali dictionary must provide every key (checked by TypeScript and by a test).
 */
export const en = {
  common: {
    appName: "Somali ERP",
    loading: "Loading…",
    retry: "Try again",
    back: "Back",
    close: "Close",
    required: "Required",
    language: "Language",
    languages: { so: "Soomaali", en: "English" },
    skipToContent: "Skip to main content",
    reference: "Reference",
    previewBanner: "PREVIEW DATA — not real data",
  },
  nav: {
    main: "Main navigation",
    overview: "Overview",
    companies: "Companies",
    account: "Account",
    collapse: "Collapse sidebar",
    expand: "Expand sidebar",
    openMenu: "Open menu",
    closeMenu: "Close menu",
  },
  topbar: {
    activeCompany: "Active company",
    selectCompany: "Select company",
    switchCompany: "Switch company",
    userMenu: "User menu",
    accountSettings: "Account settings",
    signOut: "Sign out",
    signingOut: "Signing out…",
  },
  auth: {
    login: {
      title: "Sign in",
      subtitle: "Sign in to manage your business.",
      email: "Email address",
      password: "Password",
      showPassword: "Show password",
      hidePassword: "Hide password",
      submit: "Sign in",
      submitting: "Signing in…",
      forgot: "Forgot your password?",
      sessionExpired: "Your session has ended. Please sign in again.",
    },
    forgot: {
      title: "Reset your password",
      intro:
        "Enter your email address. If an account exists, we will send a link to choose a new password.",
      submit: "Send reset link",
      submitting: "Sending…",
      sentTitle: "Check your email",
      sentBody:
        "If an account exists for that address, a reset link is on its way. The link is valid for one hour.",
      backToLogin: "Back to sign in",
    },
    reset: {
      title: "Choose a new password",
      newPassword: "New password",
      confirmPassword: "Confirm new password",
      hint: "At least 10 characters. Avoid common or numbers-only passwords.",
      mismatch: "The passwords do not match.",
      submit: "Save new password",
      submitting: "Saving…",
      doneTitle: "Password changed",
      doneBody:
        "Your password has been changed and all sessions were signed out. You can now sign in with the new password.",
      invalidTitle: "This reset link cannot be used",
      invalidBody:
        "The link is invalid, already used or older than one hour. Request a new one.",
      requestNew: "Request a new link",
    },
  },
  companies: {
    selectTitle: "Select a company",
    selectIntro: "Choose the company you want to work in.",
    noneTitle: "No companies available",
    noneBody:
      "Your account is not an active member of any company. Ask your administrator for an invitation.",
    business: "Business",
    unavailable: "That company is not available. Choose another one.",
    open: "Open",
    opening: "Opening…",
    current: "Current",
  },
  home: {
    title: "Overview",
    welcome: (name: string) => `Welcome, ${name}`,
    companyDetails: "Company details",
    legalName: "Legal name",
    tradeName: "Trade name",
    code: "Code",
    baseCurrency: "Base currency",
    country: "Country",
    timezone: "Time zone",
    fiscalYearStart: "Fiscal year starts in",
    signedInAs: "Signed in as",
    quickActions: "Quick actions",
    modulesTitle: "Business modules",
    modulesBody:
      "Sales, purchasing, inventory and accounting will appear here when those modules are released.",
  },
  account: {
    title: "Account",
    profile: "Profile",
    email: "Email address",
    fullName: "Full name",
    notSet: "Not set",
    changePassword: "Change password",
    currentPassword: "Current password",
    success: "Your password has been changed. Your other sessions were signed out.",
    backToCompany: "Back to company",
  },
  status: {
    title: "System status",
    api: "API",
    database: "Database",
    states: {
      ok: "Operational",
      error: "Error",
      unavailable: "Unavailable",
      unreachable: "Unreachable",
      unknown: "Unknown",
    },
  },
  errors: {
    invalid_credentials: "Incorrect email or password.",
    invalid_current_password: "The current password is incorrect.",
    throttled: "Too many attempts. Please wait and try again.",
    throttledWait: (minutes: number) =>
      `Too many attempts. Try again in ${minutes} ${minutes === 1 ? "minute" : "minutes"}.`,
    csrf_failed: "Your security token has expired. Reload the page and try again.",
    not_authenticated: "Please sign in.",
    validation_error: "Please check the highlighted fields.",
    service_unavailable: "The service is temporarily unavailable. Please try again.",
    not_found: "Not found.",
    network_error: "Cannot reach the server. Check your connection and try again.",
    server_error: "Something went wrong on the server. Please try again.",
    unknown: "Something went wrong. Please try again.",
  },
  pages: {
    notFoundTitle: "Page not found",
    notFoundBody: "The page does not exist or you do not have access to it.",
    goHome: "Go to the start page",
    errorTitle: "Something went wrong",
    errorBody: "An unexpected error occurred. Try again; if it keeps happening, contact support.",
  },
};

type Widen<T> = T extends string
  ? string
  : T extends (...args: infer A) => string
    ? (...args: A) => string
    : { [K in keyof T]: Widen<T[K]> };

export type Messages = Widen<typeof en>;
