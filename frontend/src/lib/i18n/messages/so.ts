import type { Messages } from "./en";

/**
 * Somali messages (default language, decision D8).
 *
 * Review status (decision D12): every string in this file is a draft written by Claude and
 * **needs review** by a Somali speaker before the pilot. Change `reviewStatus` to
 * "reviewed" only after that review.
 */
export const reviewStatus: "needs-review" | "reviewed" = "needs-review";

export const so: Messages = {
  common: {
    appName: "Somali ERP",
    loading: "Waa la soo rarayaa…",
    retry: "Isku day mar kale",
    back: "Dib u noqo",
    close: "Xir",
    required: "Waa qasab",
    language: "Luqadda",
    languages: { so: "Soomaali", en: "English" },
    skipToContent: "U gudub nuxurka bogga",
    reference: "Tixraac",
    previewBanner: "XOG TUSAALE AH — xog dhab ah maaha",
  },
  nav: {
    main: "Hagaha guud",
    overview: "Guudmar",
    companies: "Shirkadaha",
    account: "Akoonka",
    collapse: "Yaree liiska dhinaca",
    expand: "Ballaadhi liiska dhinaca",
    openMenu: "Fur liiska",
    closeMenu: "Xir liiska",
  },
  topbar: {
    activeCompany: "Shirkadda firfircoon",
    selectCompany: "Dooro shirkad",
    switchCompany: "Beddel shirkadda",
    userMenu: "Liiska isticmaalaha",
    accountSettings: "Dejinta akoonka",
    signOut: "Ka bax",
    signingOut: "Waa la baxayaa…",
  },
  auth: {
    login: {
      title: "Soo gal",
      subtitle: "Soo gal si aad u maamusho ganacsigaaga.",
      email: "Ciwaanka iimaylka",
      password: "Erayga sirta ah",
      showPassword: "Muuji erayga sirta ah",
      hidePassword: "Qari erayga sirta ah",
      submit: "Soo gal",
      submitting: "Waa la soo galayaa…",
      forgot: "Ma ilowday erayga sirta ah?",
      sessionExpired: "Fadhigaagu wuu dhammaaday. Fadlan mar kale soo gal.",
    },
    forgot: {
      title: "Dib u dej erayga sirta ah",
      intro:
        "Geli ciwaanka iimaylkaaga. Haddii akoon jiro, waxaan kuu soo diri doonnaa xiriiriye aad ku dooran karto eray sir ah oo cusub.",
      submit: "Dir xiriiriyaha",
      submitting: "Waa la dirayaa…",
      sentTitle: "Hubi iimaylkaaga",
      sentBody:
        "Haddii akoon ku diiwaangashan yahay ciwaankaas, xiriiriye dib-u-dejin ah ayaa kuu imanaya. Xiriiriyuhu wuxuu shaqaynayaa hal saac.",
      backToLogin: "Ku noqo soo galka",
    },
    reset: {
      title: "Dooro eray sir ah oo cusub",
      newPassword: "Erayga sirta ah ee cusub",
      confirmPassword: "Xaqiiji erayga sirta ah ee cusub",
      hint: "Ugu yaraan 10 xaraf. Ka fogow erayo caadi ah ama tiro keliya.",
      mismatch: "Erayada sirta ahi isma laha.",
      submit: "Kaydi erayga sirta ah",
      submitting: "Waa la kaydinayaa…",
      doneTitle: "Erayga sirta ah waa la beddelay",
      doneBody:
        "Erayga sirta ah waa la beddelay, dhammaan fadhiyadiina waa la xiray. Hadda waxaad ku soo geli kartaa erayga cusub.",
      invalidTitle: "Xiriiriyahan lama isticmaali karo",
      invalidBody:
        "Xiriiriyuhu waa khalad, hore ayaa loo isticmaalay ama wuxuu dhaafay hal saac. Codso mid cusub.",
      requestNew: "Codso xiriiriye cusub",
    },
  },
  companies: {
    selectTitle: "Dooro shirkad",
    selectIntro: "Dooro shirkadda aad rabto inaad ka shaqayso.",
    noneTitle: "Shirkad lama heli karo",
    noneBody:
      "Akoonkaagu xubin firfircoon kama aha shirkad. Maamulahaaga ka codso martiqaad.",
    business: "Ganacsiga",
    unavailable: "Shirkaddaas lama heli karo. Dooro mid kale.",
    open: "Fur",
    opening: "Waa la furayaa…",
    current: "Hadda",
  },
  home: {
    title: "Guudmar",
    welcome: (name: string) => `Ku soo dhowow, ${name}`,
    companyDetails: "Faahfaahinta shirkadda",
    legalName: "Magaca sharciga",
    tradeName: "Magaca ganacsiga",
    code: "Koodh",
    baseCurrency: "Lacagta aasaasiga ah",
    country: "Dalka",
    timezone: "Waqtiga deegaanka",
    fiscalYearStart: "Sannadka maaliyaddu wuxuu bilaabmaa",
    signedInAs: "Waxaad ku soo gashay",
    quickActions: "Ficillo degdeg ah",
    modulesTitle: "Qaybaha ganacsiga",
    modulesBody:
      "Iibka, iibsiga, kaydka alaabta iyo xisaabaadku halkan ayay ka muuqan doonaan marka qaybahaas la sii daayo.",
  },
  account: {
    title: "Akoonka",
    profile: "Xogta shakhsiga",
    email: "Ciwaanka iimaylka",
    fullName: "Magaca buuxa",
    notSet: "Lama gelin",
    changePassword: "Beddel erayga sirta ah",
    currentPassword: "Erayga sirta ah ee hadda",
    success: "Erayga sirta ah waa la beddelay. Fadhiyadaada kale waa la xiray.",
    backToCompany: "Ku noqo shirkadda",
  },
  status: {
    title: "Xaaladda nidaamka",
    api: "API",
    database: "Kaydka xogta",
    states: {
      ok: "Wuu shaqaynayaa",
      error: "Khalad",
      unavailable: "Lama heli karo",
      unreachable: "Lama gaari karo",
      unknown: "Lama garanayo",
    },
  },
  errors: {
    invalid_credentials: "Iimaylka ama erayga sirta ah waa khalad.",
    invalid_current_password: "Erayga sirta ah ee hadda waa khalad.",
    throttled: "Isku dayo badan. Fadlan sug oo mar kale isku day.",
    throttledWait: (minutes: number) =>
      `Isku dayo badan. Mar kale isku day ${minutes} daqiiqo kadib.`,
    csrf_failed: "Calaamadda amniga ayaa dhacday. Dib u soo rar bogga oo mar kale isku day.",
    not_authenticated: "Fadlan soo gal.",
    validation_error: "Fadlan hubi meelaha la calaamadeeyay.",
    service_unavailable: "Adeeggu si ku meel gaar ah uma shaqaynayo. Fadlan mar kale isku day.",
    not_found: "Lama helin.",
    network_error: "Server-ka lama gaari karo. Hubi xiriirkaaga oo mar kale isku day.",
    server_error: "Khalad ayaa ka dhacay server-ka. Fadlan mar kale isku day.",
    unknown: "Wax baa khaldamay. Fadlan mar kale isku day.",
  },
  pages: {
    notFoundTitle: "Bogga lama helin",
    notFoundBody: "Boggani ma jiro ama ma lihid ogolaansho aad ku gasho.",
    goHome: "Tag bogga bilowga",
    errorTitle: "Wax baa khaldamay",
    errorBody:
      "Khalad lama filaan ah ayaa dhacay. Mar kale isku day; haddii uu sii socdo, la xiriir taageerada.",
  },
};
