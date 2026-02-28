import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Info,
  Briefcase,
  Bookmark,
  Flag,
  Share2,
  X,
  Check,
  DollarSign,
  Clock,
  ChevronDown,
  MapPinOff,
  MapPin,
  MessageCircle,
  GalleryHorizontalEnd,
  MoreHorizontal,
  Navigation,
  Star,
  Plane,
  Send,
  Phone,
  Laptop,
  Banknote,
  MapPinned,
  Copy,
  User,
  Building,
  Layers,
  ExternalLink,
  Loader2,
  MoreVertical,
  ArrowLeft,
  AlertTriangle,
} from "lucide-react";
import FlyerView from "./FlyerView"; // Ajusta la ruta según donde guardes el componente
import { createPortal } from "react-dom";
import { Trash2 } from "lucide-react";
import {
  deleteDoc,
  doc,
  addDoc,
  collection,
  serverTimestamp,
  setDoc,
  getDoc,
} from "firebase/firestore";
import { db } from "./firebase/firebase";
import { CheckCircle } from "lucide-react";

import { XCircle } from "lucide-react"; // ← Agregar XCircle

import { Swiper, SwiperSlide } from "swiper/react";
import { Pagination } from "swiper/modules";
// Lazy-load photo lightbox to shrink initial bundle
const PhotoProvider = React.lazy(() => import("react-photo-view").then(m => ({ default: m.PhotoProvider })));
const PhotoView = React.lazy(() => import("react-photo-view").then(m => ({ default: m.PhotoView })));
import ColorThief from "colorthief";
import { Mail, Globe, Building2, Users, Wallet, FileText } from "lucide-react";
import JobMapView from "./JobMapView";
import JobContactView from "./JobContactView";
import JobDetailView from "./JobDetailView";
import Linkify from "linkify-react";
import mapActiveSvg from "./assets/job-map-icon.svg";
import { isSavedJob } from "./utils/savedJobs";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSaveMutation } from "./utils/saveMutations";
import { useJobCreators } from "./hooks/useJobCreators";
import { text } from "linkifyjs";

export default function JobCard({
  job,
  isSaved,
  onSave,
  setShowMap,
  onColorChange,
  initialColor,
  parentSwiperRef,
  userId, // ← Agregar esto
  onJobRemoved, // ← Nueva prop
  setShowLoginModal, // ← Nueva prop para mostrar modal de login
  isMapMode, // ← Nueva prop para modo mapa
  updateNotificationId, // ← Opcional: id de notificación a marcar como leída
  onMarkNotificationRead, // ← Opcional: callback del padre para marcar como leída
  notificationCollection = "notifications", // ← Opcional: colección de notificaciones
}) {
  // Formatea la fecha para mostrar "Hoy", "Ayer" y luego día + mes;
  // incluye el año solo si no es el año actual.
  const formatRelativeDate = (createdAt) => {
    if (!createdAt) return "Fecha no disponible";
    let date;
    try {
      date = createdAt?.toDate ? createdAt.toDate() : new Date(createdAt);
      if (isNaN(date?.getTime?.())) return "Fecha no disponible";
    } catch (e) {
      return "Fecha no disponible";
    }

    const now = new Date();
    const startOfToday = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate()
    );
    const startOfTomorrow = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() + 1
    );
    const startOfYesterday = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() - 1
    );

    if (date >= startOfToday && date < startOfTomorrow) return "Hoy";
    if (date >= startOfYesterday && date < startOfToday) return "Ayer";

    const months = [
      "enero",
      "febrero",
      "marzo",
      "abril",
      "mayo",
      "junio",
      "julio",
      "agosto",
      "septiembre",
      "octubre",
      "noviembre",
      "diciembre",
    ];
    const day = date.getDate();
    const month = months[date.getMonth()];
    const year = date.getFullYear();
    return year === now.getFullYear()
      ? `${day} de ${month}`
      : `${day} de ${month} de ${year}`;
  };
  /*   useEffect(() => {
      console.log("[job-card] props recibidas:", {
        jobId: job?.id,
        images: job?.images,
        url: job?.url,
        hasImages: Array.isArray(job?.images) ? job.images.length : "no-array",
      });
    }, [job]); */

  // moved below to avoid TDZ with showActionsMenu
  const defaultDominantColor = "rgba(255, 255, 255, 1)";
  const [dominantColor, setDominantColor] = useState(
    initialColor || defaultDominantColor,
  );
  const [imageLoadState, setImageLoadState] = useState({});
  const [activeModal, setActiveModal] = useState("gallery"); // 'gallery', 'map', 'contact', 'details'
  const swiperRef = useRef(null);
  const colorThiefRef = useRef(new ColorThief());
  const parentSwiperEnabledRef = useRef(null);
  const flyerColorRef = useRef(null);
  const [isInfoExpanded, setIsInfoExpanded] = useState(false);
  const [datosExpanded, setDatosExpanded] = useState(false);
  const [ubicacionExpanded, setUbicacionExpanded] = useState(false);
  const [contactoExpanded, setContactoExpanded] = useState(false);
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);
  const [activeSection, setActiveSection] = useState(null); // null, 'description', 'datos', 'ubicacion', 'contacto'
  // Defer heavy CSS to after initial paint to improve LCP
  useEffect(() => {
    // Load gallery/map related CSS only when the first card mounts
    // This keeps initial CSS smaller and avoids render-blocking
    import('swiper/css');
    import('swiper/css/pagination');
    import('react-photo-view/dist/react-photo-view.css');
  }, []);
  const queryClient = useQueryClient();
  const saveMutation = useMutation(createSaveMutation(userId, queryClient));
  const userData_query = queryClient.getQueryData(["userData", userId]);
  const actualIsSaved = userData_query
    ? isSavedJob(userData_query.saved, job.id)
    : isSaved;
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  // Después de la línea: const actualIsSaved = userData_query?.saved?.includes(job.id) ?? isSaved;
  const isOwner =
    userId && (job.userId === userId || userData_query?.role === "admin");
  const [deleteSuccess, setDeleteSuccess] = useState(false);
  const { data: creatorsMap = {} } = useJobCreators(
    job.userId ? [job.userId] : [],
  );
  const [copiedField, setCopiedField] = useState(null); // 'phone' o 'email'
  const userData = creatorsMap[job.userId];
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [reportReason, setReportReason] = useState("");
  const [reportDetails, setReportDetails] = useState("");
  const [reportSubmitted, setReportSubmitted] = useState(false);
  const [reportError, setReportError] = useState("");
  const [isSubmittingReport, setIsSubmittingReport] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [shareError, setShareError] = useState("");
  const [shareLink, setShareLink] = useState("");
  const [showShareModal, setShowShareModal] = useState(false);
  const [hasCopiedShareLink, setHasCopiedShareLink] = useState(false);
  const [showActionsMenu, setShowActionsMenu] = useState(false);
  const [isTogglingActive, setIsTogglingActive] = useState(false);
  const [showDisableModal, setShowDisableModal] = useState(false);
  const [showEnableModal, setShowEnableModal] = useState(false);
  const [isDisabling, setIsDisabling] = useState(false);
  const [isEnabling, setIsEnabling] = useState(false);
  const [localIsActive, setLocalIsActive] = useState(job?.isActive !== false);
  const actionsMenuRef = useRef(null);
  const actionsMenuButtonRef = useRef(null);
  const actionsMenuPortalRef = useRef(null);
  const [actionsMenuPos, setActionsMenuPos] = useState({ top: 0, left: 0 });
  const updateActionsMenuPosition = useCallback(() => {
    try {
      const btn = actionsMenuButtonRef.current;
      if (!btn) return;
      const rect = btn.getBoundingClientRect();
      const MENU_WIDTH = 192; // Tailwind w-48 (12rem)
      const PADDING = 8;
      let left = rect.right - MENU_WIDTH;
      left = Math.min(
        Math.max(PADDING, left),
        (window.innerWidth || document.documentElement.clientWidth) - MENU_WIDTH - PADDING,
      );
      const top = rect.bottom + 8;
      setActionsMenuPos({ top, left });
    } catch { }
  }, []);
  useEffect(() => {
    if (!showActionsMenu) return;
    updateActionsMenuPosition();
    const onReposition = () => updateActionsMenuPosition();
    window.addEventListener('resize', onReposition);
    window.addEventListener('scroll', onReposition, true);
    return () => {
      window.removeEventListener('resize', onReposition);
      window.removeEventListener('scroll', onReposition, true);
    };
  }, [showActionsMenu, updateActionsMenuPosition]);

  const handleToggleActionsMenu = useCallback(() => {
    setShowActionsMenu((prev) => {
      if (prev) return false;
      updateActionsMenuPosition();
      return true;
    });
  }, [updateActionsMenuPosition]);
  useEffect(() => {
    const handleClickOutside = (event) => {
      const anchor = actionsMenuRef.current;
      const menu = actionsMenuPortalRef?.current;
      if (!showActionsMenu) return;
      const target = event.target;
      if ((anchor && anchor.contains(target)) || (menu && menu.contains(target))) {
        return;
      }
      setShowActionsMenu(false);
    };
    document.addEventListener("mousedown", handleClickOutside, true);
    document.addEventListener("touchstart", handleClickOutside, true);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside, true);
      document.removeEventListener("touchstart", handleClickOutside, true);
    };
  }, [showActionsMenu]); const lastPersistedColorRef = useRef(
    job?.dominantColor || initialColor || null,
  );
  const isPersistingColorRef = useRef(false);
  const pendingColorRef = useRef(null);
  const initialPersistRef = useRef(false);
  const normalizedUbication = useMemo(() => {
    const u = job?.ubication;
    if (u && u.lat != null && u.lng != null) {
      return u;
    }
    if (job?.lat != null && job?.lng != null) {
      return {
        lat: Number(job.lat),
        lng: Number(job.lng),
        address: job?.address || "",
        placeId: job?.placeId || "",
      };
    }
    return null;
  }, [job]);
  const hasMap = !!(normalizedUbication && normalizedUbication.lat != null && normalizedUbication.lng != null);
  const [activeSlideIndex, setActiveSlideIndex] = useState(hasMap ? 1 : 0);
  useEffect(() => {
    try {
      /*      console.log("[job-card] hasMap check", {
              jobId: job?.id,
              hasMap,
              normalizedUbication,
              rawUbication: job?.ubication || null,
              rootLatLng: { lat: job?.lat ?? null, lng: job?.lng ?? null },
              initialSlide: hasMap ? 1 : 0,
            }); */
    } catch { }
  }, [job?.id, hasMap, normalizedUbication]);

  // Resetear el slide activo al cambiar de job o disponibilidad de mapa
  useEffect(() => {
    const targetIndex = hasMap ? 1 : 0; // 1 = primera imagen si hay mapa, 0 = mapa si no hay imágenes
    setActiveSlideIndex(targetIndex);
    if (swiperRef.current && typeof swiperRef.current.slideTo === 'function') {
      try {
        swiperRef.current.slideTo(targetIndex, 0);
        // Deshabilita swipe en el slide del mapa
        swiperRef.current.allowTouchMove = !(hasMap && targetIndex === 0);
      } catch { }
    }
  }, [job?.id, hasMap]);
  // Preparar todas las imágenes
  const allImages =
    job.images && job.images.length > 0 ? job.images : job.url ? [job.url] : [];
  const resolvedInitialColor = job?.dominantColor || initialColor || null;

  const approvalBadgeMap = {
    approved: {
      label: "Aprobado",
      classes: "bg-emerald-100 text-emerald-700 border border-emerald-200",
    },
    rejected: {
      label: "Rechazado",
      classes: "bg-rose-100 text-rose-700 border border-rose-200",
    },
    pending: {
      label: "Pendiente",
      classes: "bg-amber-100 text-amber-700 border border-amber-200",
    },
  };
  const approvalStatus = (job?.approvalStatus || "pending").toString().toLowerCase();
  const approvalBadge =
    approvalBadgeMap[approvalStatus] || approvalBadgeMap.pending;
  const publicationTypeLabels = {
    alquiler: "Alquiler",
    publicidad: "Publicidad",
    empleo: "Empleo",
  };
  const publicationTypeKey =
    typeof job?.publicationType === "string"
      ? job.publicationType.toLowerCase()
      : null;
  const isNonJobPublication =
    publicationTypeKey && publicationTypeKey !== "empleo";
  const isRentPublication =
    publicationTypeKey === "alquiler" || job?._collection === "rents";
  const publicationTypeLabel = publicationTypeKey
    ? publicationTypeLabels[publicationTypeKey]
    : null;

  useEffect(() => {
    const baseColor = resolvedInitialColor || defaultDominantColor;
    setDominantColor((previous) =>
      previous === baseColor ? previous : baseColor,
    );
    if (resolvedInitialColor) {
      lastPersistedColorRef.current = resolvedInitialColor;
    } else {
      lastPersistedColorRef.current = null;
    }
  }, [resolvedInitialColor, defaultDominantColor]);
  useEffect(() => {
    setImageLoadState({});
  }, [job?.id, job?.images, job?.url]);

  // Mantener el estado local sincronizado con el valor del job
  useEffect(() => {
    setLocalIsActive(job?.isActive !== false);
  }, [job?.id, job?.isActive]);
  const persistDominantColor = useCallback(
    async (color, context = "unknown") => {
      if (!job?.id) {
        console.warn("[job-card] Skipping dominant color persist: missing jobId", {
          context,
          color,
          jobId: job?.id,
        });
        return;
      }
      if (!color) {
        console.warn("[job-card] Skipping dominant color persist: missing color", {
          context,
          jobId: job.id,
        });
        return;
      }
      if (color === lastPersistedColorRef.current) {
        console.debug("[job-card] Dominant color already persisted", {
          context,
          color,
          jobId: job.id,
        });
        return;
      }
      if (isPersistingColorRef.current) {
        console.debug("[job-card] Persist already in progress, queueing color", {
          context,
          color,
          jobId: job.id,
        });
        pendingColorRef.current = color;
        return;
      }
      isPersistingColorRef.current = true;
      console.debug("[job-card] Persisting dominant color", {
        context,
        color,
        jobId: job.id,
      });
      try {
        if (!initialPersistRef.current) {
          console.debug("[job-card] Skipping first persist, awaiting initial check", {
            context,
            color,
            jobId: job.id,
          });
          initialPersistRef.current = true;
        }

        await setDoc(
          doc(db, "jobs", job.id),
          { dominantColor: color },
          { merge: true },
        );
        lastPersistedColorRef.current = color;
        /*         console.info("[job-card] Dominant color persisted", {
                  context,
                  color,
                  jobId: job.id,
                }); */
      } catch (error) {
        /*       console.error("[job-card] Error persisting dominant color", {
                context,
                color,
                jobId: job.id,
                error,
              }); */
      } finally {
        isPersistingColorRef.current = false;
        if (
          pendingColorRef.current &&
          pendingColorRef.current !== lastPersistedColorRef.current
        ) {
          const nextColor = pendingColorRef.current;
          pendingColorRef.current = null;
          console.debug("[job-card] Flushing queued dominant color", {
            context: "flush",
            color: nextColor,
            jobId: job.id,
          });
          persistDominantColor(nextColor, "flush");
        } else {
          pendingColorRef.current = null;
        }
      }
    },
    [job?.id],
  );
  const renderOwnerBadgeOverlay = () => {
    if (!(isOwner && isNonJobPublication)) {
      return null;
    }
    return (
      <div className="absolute left-3 bottom-3 z-30 flex flex-wrap items-center gap-2">
        <span
          className={`text-xs font-semibold px-3 py-1 rounded-full ${approvalBadge.classes}`}
          title={`Estado de aprobacion: ${approvalBadge.label}`}
        >
          {approvalBadge.label}
        </span>
        {publicationTypeLabel ? (
          <span className="text-xs bg-gray-100 text-gray-700 px-3 py-1 rounded-full">
            {publicationTypeLabel}
          </span>
        ) : null}
      </div>
    );
  };

  // Función para extraer el color dominante
  const extractDominantColor = (imgElement, meta = {}) => {
    const { source = "unknown", key = null, reason = source } =
      typeof meta === "string"
        ? { source: meta, reason: meta }
        : meta ?? {};

    if (!imgElement) {
      console.warn("[job-card] Dominant color extraction skipped: no image element", {
        jobId: job?.id,
        source,
        key,
      });
      return;
    }

    if (!imgElement.complete || imgElement.naturalHeight === 0) {
      console.debug(
        "[job-card] Dominant color extraction postponed: image not ready",
        {
          jobId: job?.id,
          source,
          key,
          complete: imgElement.complete,
          naturalHeight: imgElement.naturalHeight,
        },
      );
      return;
    }

    try {
      const tuple = colorThiefRef.current.getColor(imgElement);
      if (!Array.isArray(tuple) || tuple.length < 3) {
        console.warn("[job-card] Dominant color extraction produced invalid tuple", {
          jobId: job?.id,
          source,
          key,
          tuple,
        });
        return;
      }

      const rgbColor = `rgb(${tuple[0]}, ${tuple[1]}, ${tuple[2]})`;
      const stateChanged = dominantColor !== rgbColor;
      const persistedChanged = lastPersistedColorRef.current !== rgbColor;

      if (stateChanged) {
        console.debug("[job-card] Dominant color state updated", {
          jobId: job?.id,
          source,
          key,
          rgbColor,
        });
        setDominantColor(rgbColor);
      } else {
        console.debug("[job-card] Dominant color unchanged", {
          jobId: job?.id,
          source,
          key,
          rgbColor,
        });
      }

      if (persistedChanged) {
        persistDominantColor(rgbColor, reason ?? source ?? "extract");
      } else {
        console.debug("[job-card] Dominant color already persisted", {
          jobId: job?.id,
          source,
          key,
          rgbColor,
        });
      }

      if (onColorChange) {
        onColorChange(rgbColor);
      }
    } catch (error) {
      console.error("[job-card] Error extracting dominant color", {
        jobId: job?.id,
        source,
        key,
        error,
        crossOrigin: imgElement.crossOrigin,
        currentSrc: imgElement.currentSrc || imgElement.src,
      });
    }
  };
  const handleImageLoad = (key, event, shouldUpdateColor = true) => {
    const imgElement = event?.target ?? null;
    if (!imgElement) {
      return;
    }
    setImageLoadState((previous) => {
      if (previous[key]) {
        return previous;
      }
      return {
        ...previous,
        [key]: true,
      };
    });
    if (shouldUpdateColor) {
      extractDominantColor(imgElement, { source: "image-load", key });
    }
  };
  const infoContainerRef = useRef(null);
  const [isAnimating, setIsAnimating] = useState(false);
  // Perfil del usuario actual (para CV y mensaje por defecto)
  const [myProfile, setMyProfile] = useState(null);
  // Email via mailto (sin adjunto)

  useEffect(() => {
    const fetchMyProfile = async () => {
      try {
        if (!userId) return;
        const userRef = doc(db, "users", userId);
        const snap = await getDoc(userRef);
        if (snap.exists()) {
          setMyProfile(snap.data());
        }
      } catch (e) {
        console.warn("[job-card] No se pudo cargar el perfil del usuario:", e);
      }
    };
    fetchMyProfile();
  }, [userId]);

  const mailtoHref = useMemo(() => {
    if (!job?.email) return null;
    const subject = `Postulación: ${job?.title || ""}`.trim();

    const company = job?.company || "(EMPRESA)";
    const jobTitle = job?.title || "(TITULO DE OFERTA LABORAL)";
    const userName = myProfile?.displayName || "(NOMBRE)";

    const template =
      myProfile?.defaultMessage ||
      `Estimado equipo de (EMPRESA),\n\nLes escribo con gran interés por la vacante de (TITULO DE OFERTA LABORAL). Adjunto mi Currículum Vitae para su consideración.\nMi experiencia y habilidades se alinean con los requisitos del puesto y estoy convencido de que puedo aportar valor a su equipo.\n\nAgradezco su tiempo y quedo a su entera disposición para una futura entrevista.\n\nAtentamente,\n(NOMBRE)`;

    const message = template
      .replaceAll("(EMPRESA)", company)
      .replaceAll("(TITULO DE OFERTA LABORAL)", jobTitle)
      .replaceAll("(NOMBRE)", userName);

    const body = message;

    return `mailto:${job.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
  }, [job?.email, job?.title, job?.company, myProfile]);

  // Normaliza teléfono para WhatsApp (mover antes de whatsappHref para evitar TDZ)
  const cleanPhoneForWhatsApp = (phone) => {
    if (!phone) return "";
    let cleaned = String(phone).replace(/[\s\-\(\)\+]/g, "");
    if (cleaned.startsWith("0")) cleaned = cleaned.substring(1);
    if (!cleaned.startsWith("595")) cleaned = "595" + cleaned;
    return cleaned;
  };

  const whatsappHref = useMemo(() => {
    if (!job?.phoneNumber) return null;
    const phone = cleanPhoneForWhatsApp(job.phoneNumber);

    const company = job?.company || "(EMPRESA)";
    const jobTitle = job?.title || "(TITULO DE OFERTA LABORAL)";
    const userName = myProfile?.displayName || "(NOMBRE)";

    const template =
      myProfile?.defaultMessage ||
      `Estimado equipo de (EMPRESA),\n\nLes escribo con gran interés por la vacante de (TITULO DE OFERTA LABORAL). Adjunto mi Currículum Vitae para su consideración.\nMi experiencia y habilidades se alinean con los requisitos del puesto y estoy convencido de que puedo aportar valor a su equipo.\n\nAgradezco su tiempo y quedo a su entera disposición para una futura entrevista.\n\nAtentamente,\n(NOMBRE)`;

    const message = template
      .replaceAll("(EMPRESA)", company)
      .replaceAll("(TITULO DE OFERTA LABORAL)", jobTitle)
      .replaceAll("(NOMBRE)", userName);

    return `https://api.whatsapp.com/send?phone=${phone}&text=${encodeURIComponent(message)}`;
  }, [job?.phoneNumber, job?.company, job?.title, myProfile]);

  // sin manejador especial; se usará mailtoHref directamente
  const goToMapSlide = useCallback(() => {
    if (!hasMap) return;
    try {
      const swiper = swiperRef.current;
      console.log('[job-card] GoToMap button: slideTo(0)', { jobId: job?.id, hasSwiper: !!swiper });
      swiper?.slideTo?.(0, 0);
      // Fallback: si no cambia el índice, abrir overlay de mapa
      setTimeout(() => {
        const idx = swiperRef.current?.activeIndex;
        if (idx !== 0) {
          console.warn('[job-card] slideTo(0) no cambió el índice. Abriendo overlay mapa.', { currentIndex: idx, jobId: job?.id });
          setActiveModal('map');
        }
      }, 250);
    } catch (e) {
      console.warn('[job-card] GoToMap error, abriendo overlay mapa', e);
      setActiveModal('map');
    }
  }, [hasMap, job?.id]);

  // Agregar este useEffect en JobCard

  const handleSave = () => {
    // Check if user is logged in
    if (!userId) {
      if (setShowLoginModal) {
        setShowLoginModal(true);
      }
      return;
    }

    const wasAlreadySaved = actualIsSaved;

    // Reproducir sonido y animación solo cuando se GUARDA (no cuando se quita)
    if (!wasAlreadySaved) {
      setIsAnimating(true);

      // Sonido de "pop" o "click"
      const audio = new Audio(
        "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
      );
      audio.volume = 0.3;
      audio.play().catch((err) => console.log("Audio bloqueado:", err));

      setTimeout(() => setIsAnimating(false), 500);
    }

    // Si hay userId, usar mutación interna
    if (userId) {
      // ← NUEVO: Guardar el estado anterior
      const wasAlreadySaved = actualIsSaved;

      saveMutation.mutate({ jobId: job.id, isSaved: actualIsSaved });
      /* // console.log("🔖 Job guardado:", job.title); */

      // ← NUEVO: Si se está eliminando un favorito, notificar al padre
      if (wasAlreadySaved && onJobRemoved) {
        onJobRemoved(job.id);
      }
    } else {
      /* console.warn('No se puede guardar: falta userId y onSave'); */
    }
  };

  const handleReportModalClose = () => {
    setShowReportModal(false);
    setReportError("");
    setReportReason("");
    setReportDetails("");
    setIsSubmittingReport(false);
  };

  const handleReportSubmit = async (event) => {
    event.preventDefault();

    if (!userId) {
      setReportError(
        "Debes iniciar sesión para reportar esta publicación.",
      );
      return;
    }

    if (!reportReason) {
      setReportError("Selecciona un motivo antes de continuar.");
      return;
    }

    setReportError("");
    setIsSubmittingReport(true);

    try {
      await addDoc(collection(db, "jobReports"), {
        jobId: job?.id ?? null,
        jobTitle: job?.title ?? "",
        jobOwnerId: job?.userId ?? null,
        reason: reportReason,
        details: reportDetails.trim(),
        reporterId: userId ?? null,
        reporterRole: userData_query?.role ?? null,
        reporterDisplayName: userData_query?.displayName ?? null,
        reporterEmail: userData_query?.email ?? null,
        createdAt: serverTimestamp(),
        status: "pending",
      });

      setReportSubmitted(true);
      handleReportModalClose();
    } catch (error) {
      console.error("Error al registrar reporte:", error);
      setReportError("No pudimos enviar el reporte. Intenta de nuevo.");
    } finally {
      setIsSubmittingReport(false);
    }
  };

  const handleCloseReportSuccess = () => {
    setReportSubmitted(false);
  };

  const copyTextToClipboard = async (text) => {
    if (!text) return false;

    try {
      if (
        typeof navigator !== "undefined" &&
        navigator.clipboard &&
        navigator.clipboard.writeText
      ) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch (error) {
      console.warn("Clipboard API no disponible:", error);
    }

    try {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.setAttribute("readonly", "");
      textarea.style.position = "absolute";
      textarea.style.left = "-9999px";
      document.body.appendChild(textarea);
      textarea.select();
      const successful = document.execCommand("copy");
      document.body.removeChild(textarea);
      return successful;
    } catch (error) {
      console.error("No se pudo copiar el enlace:", error);
      return false;
    }
  };

  const handleShare = async () => {
    setShowActionsMenu(false);

    if (!job?.id) return;

    if (!userId) {
      setShareError("Debes iniciar sesión para compartir esta publicación.");
      setShareLink("");
      setHasCopiedShareLink(false);
      setShowShareModal(true);
      return;
    }

    setShareError("");
    setHasCopiedShareLink(false);
    setIsSharing(true);

    try {
      const rawImages = Array.isArray(job?.images)
        ? [...job.images]
        : job?.images
          ? [job.images]
          : [];

      if (job?.url) {
        rawImages.push(job.url);
      }

      if (job?.flyerImage) {
        rawImages.push(job.flyerImage);
      }

      if (job?.image) {
        rawImages.push(job.image);
      }

      const cleanedImages = rawImages
        .map((value) => (typeof value === "string" ? value.trim() : ""))
        .filter(Boolean)
        .filter((value, index, array) => array.indexOf(value) === index)
        .slice(0, 10);
      const primaryImage =
        cleanedImages[0] ??
        (job?.url ? job.url : "");

      console.log("[share] imágenes originales recibidas:", {
        jobId: job.id,
        rawImages,
        cleanedImages,
        primaryImage,
      });

      const shareDocRef = await addDoc(collection(db, "jobShares"), {
        jobId: job.id,
        createdBy: userId,
        createdAt: serverTimestamp(),
        jobTitle: job?.title ?? "",
        jobCompany: job?.company ?? "",
        jobImages: cleanedImages,
        jobImage: primaryImage ?? "",
        jobDescription: job?.description ?? "",
        jobCity: job?.city ?? "",
        jobDirection: job?.direction ?? "",
        jobModality: job?.modality ?? job?.type ?? "",
        jobVacancies: isRentPublication ? null : (job?.vacancies ?? null),
        jobSalary: job?.salary_range ?? job?.salary ?? "",
        jobPhone: job?.phoneNumber ?? "",
        jobWhatsapp: job?.whatsapp ?? "",
        jobEmail: job?.email ?? "",
        jobWebsite: job?.website ?? "",
        jobUbication:
          job?.ubication && typeof job.ubication === "object"
            ? {
              lat: job.ubication.lat ?? null,
              lng: job.ubication.lng ?? null,
              address: job.ubication.address ?? "",
              placeId: job.ubication.placeId ?? "",
            }
            : null,
      });

      /*       console.log("[share] documento creado en jobShares:", {
              shareId: shareDocRef.id,
              jobId: job.id,
              storedImages: cleanedImages,
              primaryImage,
            }); */

      const generatedLink = `${window.location.origin}/share/${shareDocRef.id}`;
      setShareLink(generatedLink);

      let sharedSuccessfully = false;

      if (typeof navigator !== "undefined" && navigator.share) {
        try {
          await navigator.share({
            title: job?.title ?? "Oportunidad en ConectaEmpleo",
            text: job?.company
              ? `${job.company} - ${job.title ?? ""}`
              : job?.title ?? "Revisa esta publicación en ConectaEmpleo",
            url: generatedLink,
          });
          sharedSuccessfully = true;
        } catch (error) {
          if (error?.name !== "AbortError") {
            console.warn("Fallo al usar navigator.share:", error);
          }
        }
      }

      if (!sharedSuccessfully) {
        const copied = await copyTextToClipboard(generatedLink);
        setHasCopiedShareLink(copied);
      }

      setShowShareModal(true);
    } catch (error) {
      console.error("Error al generar enlace para compartir:", error);
      setShareError("No pudimos crear el enlace. Intenta nuevamente.");
      setShareLink("");
      setShowShareModal(true);
    } finally {
      setIsSharing(false);
    }
  };

  const handleCloseShareModal = () => {
    setShowShareModal(false);
    setShareError("");
    setHasCopiedShareLink(false);
  };

  const handleCopyShareLink = async () => {
    if (!shareLink) return;
    const copied = await copyTextToClipboard(shareLink);
    setHasCopiedShareLink(copied);
  };

  // Owner-only: toggle availability (isActive)
  const handleToggleAvailability = async () => {
    if (!isOwner || !job?.id) return;
    const currentActive = localIsActive; // usar estado local para reflejar cambios inmediatos
    // If we are about to disable, ask for confirmation instead of toggling immediately
    if (currentActive) {
      setShowDisableModal(true);
      return;
    }
    // Enabling path: show confirmation modal
    setShowEnableModal(true);
  };

  const handleConfirmDisableAvailability = async () => {
    if (!isOwner || !job?.id) return;
    try {
      setIsDisabling(true);
      await setDoc(
        doc(db, "jobs", job.id),
        { isActive: false, updatedAt: serverTimestamp() },
        { merge: true },
      );
      try {
        window.dispatchEvent(
          new CustomEvent("job-availability-updated", {
            detail: { id: job.id, isActive: false },
          }),
        );
      } catch { }
      queryClient.invalidateQueries(["jobs"]);
      queryClient.invalidateQueries(["search-jobs"]);
      setLocalIsActive(false);
      await markUpdateNotificationRead();
      setShowDisableModal(false);
      setShowActionsMenu(false);
    } catch (err) {
      console.error("Error al deshabilitar disponibilidad:", err);
    } finally {
      setIsDisabling(false);
    }
  };

  const handleConfirmEnableAvailability = async () => {
    if (!isOwner || !job?.id) return;
    try {
      setIsEnabling(true);
      await setDoc(
        doc(db, "jobs", job.id),
        { isActive: true, updatedAt: serverTimestamp() },
        { merge: true },
      );
      try {
        window.dispatchEvent(
          new CustomEvent("job-availability-updated", {
            detail: { id: job.id, isActive: true },
          }),
        );
      } catch { }
      queryClient.invalidateQueries(["jobs"]);
      queryClient.invalidateQueries(["search-jobs"]);
      setLocalIsActive(true);
      await markUpdateNotificationRead();
      setShowEnableModal(false);
      setShowActionsMenu(false);
    } catch (err) {
      console.error("Error al habilitar disponibilidad:", err);
    } finally {
      setIsEnabling(false);
    }
  };

  // Función para limpiar el número de teléfono para WhatsApp

  // Cargar el color de la primera imagen disponible con reintentos
  useEffect(() => {
    if (allImages.length > 0) {
      const img = new Image();
      img.crossOrigin = "Anonymous";
      img.src = allImages[0];
      img.onload = () => {
        handleImageLoad("preload", { target: img }, true);
      };

      // Si falla, reintentar cuando vuelva la conexión
      img.onerror = () => {
        const retryLoad = () => {
          const retryImg = new Image();
          retryImg.crossOrigin = "Anonymous";
          retryImg.src = allImages[0];
          retryImg.onload = () => {
            handleImageLoad("preload", { target: retryImg }, true);
          };
        };

        // Escuchar evento de conexión restaurada
        const handleOnline = () => {
          retryLoad();
          window.removeEventListener("online", handleOnline);
        };
        window.addEventListener("online", handleOnline);

        // También reintentar después de 3 segundos por si acaso
        setTimeout(retryLoad, 3000);
      };
    }
  }, [job.images, job.url]);
  // Agregar esta función después de handleSave
  // Agregar esta función después de handleSave
  const handleDeleteJob = async () => {
    setIsDeleting(true);
    try {
      // 1) Eliminar imágenes del Storage (soporta job.images[], job.url y job.image)
      const { ref: storageRef, deleteObject } = await import('firebase/storage');
      const { storage } = await import('./firebase/firebase');

      // Recolectar posibles URLs de imágenes del job
      const urls = new Set();
      if (Array.isArray(job?.images)) {
        job.images.filter(Boolean).forEach((u) => urls.add(u));
      }
      if (job?.url) urls.add(job.url);
      if (job?.image) urls.add(job.image);

      // Helper para extraer path válido desde URL de descarga o gs://
      const toStorageRef = (url) => {
        try {
          if (!url || typeof url !== 'string') return null;
          // gs://bucket/path -> ref admite gs:// directamente
          if (url.startsWith('gs://')) {
            return storageRef(storage, url);
          }
          // https://firebasestorage.googleapis.com/v0/b/<bucket>/o/<path>?...
          if (url.includes('/o/')) {
            const raw = url.split('/o/')[1];
            if (!raw) return null;
            const beforeQuery = raw.split('?')[0];
            if (!beforeQuery) return null;
            const decodedPath = decodeURIComponent(beforeQuery);
            return storageRef(storage, decodedPath);
          }
          return null;
        } catch (_) {
          return null;
        }
      };

      const deletePromises = Array.from(urls).map(async (imageUrl) => {
        const refOrNull = toStorageRef(imageUrl);
        if (!refOrNull) return; // Ignora URLs no-storage
        try {
          await deleteObject(refOrNull);
        } catch (imgError) {
          console.warn('Error al eliminar imagen:', { imageUrl, message: imgError?.message || imgError });
        }
      });
      await Promise.all(deletePromises);

      // 2) Eliminar documento de Firestore desde la colección correcta
      // Detectar colección según publicationType o marcador interno
      const publicationTypeKey = typeof job?.publicationType === 'string' ? job.publicationType.toLowerCase() : null;
      const isRent = publicationTypeKey === 'alquiler' || job?._collection === 'rents';
      const isAd = publicationTypeKey === 'publicidad' || job?._collection === 'advertising';
      const collectionName = isRent ? 'rents' : isAd ? 'advertising' : 'jobs';

      await deleteDoc(doc(db, collectionName, job.id));

      // 3) Invalidar queries relacionadas
      queryClient.invalidateQueries(["jobs"]);
      queryClient.invalidateQueries(["userData", userId]);

      // 4) Marcar como leída la notificación relacionada (si viene desde notificación)
      try {
        await markUpdateNotificationRead();
      } catch { }

      setShowDeleteModal(false);
      setDeleteSuccess(true);

      setTimeout(() => {
        setDeleteSuccess(false);
        if (onJobRemoved) onJobRemoved(job.id);
      }, 2000);
    } catch (error) {
      console.error("❌ Error al eliminar el job:", error);
      setShowDeleteModal(false);
      setDeleteError(true);
      setTimeout(() => setDeleteError(false), 3000);
    } finally {
      setIsDeleting(false);
    }
  };

  // Modal de Confirmación de Borrado

  useEffect(() => {
    // console.log(userData)
  }, [userData]);

  const getContrastColor = (color) => {
    // Extraer RGB del color
    const rgbMatch = color.match(/\d+/g);
    if (!rgbMatch) return '#000000';

    const [r, g, b] = rgbMatch.map(Number);

    // Calcular luminancia (fórmula simplificada)
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;

    // Retornar negro o blanco según luminancia
    return luminance > 0.5 ? '#000000' : '#FFFFFF';
  };

  const textColor = useMemo(() => getContrastColor(dominantColor), [dominantColor]);
  const textColorClass = useMemo(() =>
    getContrastColor(dominantColor) === '#000000' ? 'text-black' : 'text-white',
    [dominantColor]);

  const availabilityBadge = useMemo(() => (
    localIsActive
      ? { label: 'Disponible', classes: 'bg-emerald-100 text-emerald-700 border border-emerald-200' }
      : { label: 'No disponible', classes: 'bg-amber-100 text-amber-700 border border-amber-200' }
  ), [localIsActive]);

  // Compatibilidad: usar `categorias` (array) si existe; de lo contrario,
  // envolver `categoria` o `category` (string) en un array de un elemento.
  const categories = useMemo(() => {
    if (Array.isArray(job?.categorias) && job.categorias.length > 0) {
      return job.categorias;
    }
    if (job?.categoria) return [job.categoria];
    if (job?.category) return [job.category];
    return [];
  }, [job?.categorias, job?.categoria, job?.category]);

  // Marca como leída la notificación por ID dentro de users/{uid}.notifications
  const markUserNotificationByIdRead = useCallback(async () => {
    if (!userId || !updateNotificationId) return false;
    try {
      const userRef = doc(db, 'users', userId);
      const snap = await getDoc(userRef);
      if (!snap.exists()) return false;
      const data = snap.data();
      const list = Array.isArray(data?.notifications) ? data.notifications : [];
      let changed = false;
      const updated = list.map((n) => {
        if (n?.id === updateNotificationId && !n?.isRead) {
          changed = true;
          return { ...n, isRead: true };
        }
        return n;
      });
      if (changed) {
        await setDoc(userRef, { notifications: updated, updatedAt: serverTimestamp() }, { merge: true });
      }
      return changed;
    } catch (e) {
      console.warn('[job-card] No se pudo marcar como leída (por ID) la notificación', e);
      return false;
    }
  }, [db, userId, updateNotificationId]);

  // Marca como leídas las notificaciones que refieren a este jobId (referenceId o metadata.jobId)
  const markRelatedNotificationsAsReadForJob = useCallback(async () => {
    if (!userId || !job?.id) return false;
    try {
      const userRef = doc(db, 'users', userId);
      const snap = await getDoc(userRef);
      if (!snap.exists()) return false;
      const data = snap.data();
      const list = Array.isArray(data?.notifications) ? data.notifications : [];
      let changed = false;
      const updated = list.map((n) => {
        const refId = n?.referenceId ?? n?.rentId ?? null;
        const metaJobId = n?.metadata?.jobId ?? null;
        if ((refId === job.id || metaJobId === job.id) && !n?.isRead) {
          changed = true;
          return { ...n, isRead: true };
        }
        return n;
      });
      if (changed) {
        await setDoc(userRef, { notifications: updated, updatedAt: serverTimestamp() }, { merge: true });
      }
      return changed;
    } catch (e) {
      console.warn('[job-card] No se pudieron marcar como leídas las notificaciones relacionadas', e);
      return false;
    }
  }, [db, userId, job?.id]);

  // Punto de entrada: intenta callback → por id → por jobId
  const markUpdateNotificationRead = useCallback(async () => {
    try {
      if (typeof onMarkNotificationRead === 'function' && updateNotificationId) {
        onMarkNotificationRead(updateNotificationId);
        return;
      }
      if (updateNotificationId) {
        const ok = await markUserNotificationByIdRead();
        if (ok) return;
      }
      await markRelatedNotificationsAsReadForJob();
    } catch (e) {
      console.warn('[job-card] No se pudo marcar como leída la notificación (fallback)', e);
    }
  }, [onMarkNotificationRead, updateNotificationId, markUserNotificationByIdRead, markRelatedNotificationsAsReadForJob]);



  return (
    <>
      <React.Suspense fallback={null}>
        <PhotoProvider maskOpacity={1}>
          <div className="mx-auto modal-card overflow-hidden relative  flex flex-col h-screen w-auto lg:min-w-auto p-2">
            {/* Header negro con información del usuario */}

            <div style={{
              backgroundColor: dominantColor,
              transition: "background-color 0.3s ease",
              position: "relative",
            }} className="w-full flex-shrink-0 z-50">

              <div className="flex items-center justify-between px-4 py-3 relative z-50">
                {/* Información del usuario a la izquierda */}
                <div className="flex items-center gap-2">
                  {hasMap && activeSlideIndex === 0 && job.uid === "1" ? (
                    <>
                      <AlertTriangle className="w-6 h-6 text-yellow-500" />
                      <p className="text-sm text-yellow-700">
                        Ubicación generada por IA - Puede contener imprecisiones.
                      </p>
                    </>
                  ) : (
                    /* Información del usuario: si no hay datos o es anónimo, mostrar placeholder */
                    userData && !userData.anonymous ? (
                      <>
                        {userData.customPhotoURL ? (
                          <img
                            src={userData.customPhotoURL}
                            alt={userData.displayName || "Usuario"}
                            className="w-6 h-6 rounded-full object-cover"
                          />
                        ) : (
                          <div
                            className="w-6 h-6 rounded-full flex items-start justify-center"
                            style={{
                              background:
                                "linear-gradient(135deg, #FE9F92 0%, #F66F71 100%)",
                            }}
                          >
                            <User
                              className="w-3 h-3 text-white mt-0.5"
                              strokeWidth={2.5}
                            />
                          </div>
                        )}
                        <div className="flex flex-col">
                          <p className="text-sm font-semibold" style={{ color: textColor }}>
                            {userData.displayName || "Usuario"}
                          </p>
                          {job.createdAt && (
                            <p className=" text-xs opacity-60" style={{ color: textColor }}>
                              {formatRelativeDate(job.createdAt)}
                            </p>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <div style={{ backgroundColor: textColor, opacity: 0.4 }} className="w-6 h-6 rounded-full" />

                        <div className="flex flex-col">
                          <p style={{ color: textColor }} className=" text-xs opacity-60">
                            {formatRelativeDate(job.createdAt)}
                          </p>
                        </div>
                      </>
                    )
                  )}
                </div>

                {/* Menú de tres puntos a la derecha */}
                <div className="relative z-50" ref={actionsMenuRef}>
                  <button
                    ref={actionsMenuButtonRef}
                    onClick={handleToggleActionsMenu}
                    className="w-8 h-8 flex items-center justify-center hover:bg-white/10 rounded-full transition-all"
                    aria-haspopup="true"
                    aria-expanded={showActionsMenu}
                    style={{ color: textColor }}
                  >
                    <MoreVertical size={20} />
                  </button>

                  {showActionsMenu &&
                    createPortal(
                      <div
                        ref={actionsMenuPortalRef}
                        className="fixed bg-white border border-gray-100 rounded-md shadow-xl z-[100000] py-2"
                        style={{ top: actionsMenuPos.top, left: actionsMenuPos.left, width: '12rem', WebkitTransform: 'translate3d(0,0,0)' }}
                      >
                        {!isRentPublication && (
                          <button
                            onClick={() => {
                              handleShare();
                              setShowActionsMenu(false);
                            }}
                            disabled={isSharing}
                            className="w-full px-4 py-2 flex items-center gap-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {isSharing ? (
                              <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                            ) : (
                              <Share2 className="w-4 h-4 text-blue-500" />
                            )}
                            <span>Compartir</span>
                          </button>
                        )}

                        {/* Toggle disponibilidad (solo dueño y solo para empleos) */}
                        {isOwner && !isNonJobPublication && (
                          <button
                            onClick={handleToggleAvailability}
                            disabled={isTogglingActive}
                            className="w-full px-4 py-2 flex items-center gap-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                          >
                            {!localIsActive ? (
                              <CheckCircle className="w-4 h-4 text-emerald-600" />
                            ) : (
                              <XCircle className="w-4 h-4 text-gray-500" />
                            )}
                            <span>
                              {localIsActive ? "No disponible" : "Disponible"}
                            </span>
                          </button>
                        )}

                        <button
                          onClick={() => {
                            setShowActionsMenu(false);
                            if (!userId) {
                              setShareError(
                                "Debes iniciar sesión para reportar esta publicación.",
                              );
                              setShareLink("");
                              setHasCopiedShareLink(false);
                              setShowShareModal(true);
                              return;
                            }
                            setShowReportModal(true);
                          }}
                          className="w-full px-4 py-2 flex items-center gap-3 text-sm text-gray-700 hover:bg-gray-50"
                        >
                          <Flag className="w-4 h-4 text-orange-500" />
                          <span>Reportar</span>
                        </button>

                        {isOwner && (
                          <button
                            onClick={() => {
                              setShowActionsMenu(false);
                              setShowDeleteModal(true);
                            }}
                            className="w-full px-4 py-2 flex items-center gap-3 text-sm text-rose-600 hover:bg-rose-50"
                          >
                            <Trash2 className="w-4 h-4" />
                            <span>Eliminar</span>
                          </button>
                        )}
                      </div>,
                      document.body,
                    )}

                  {false && showActionsMenu && (
                    <div className="absolute right-0 top-10 w-48 bg-white border border-gray-100 rounded-md shadow-xl z-[99999] py-2">
                      {!isRentPublication && (
                        <button
                          onClick={() => {
                            handleShare();
                            setShowActionsMenu(false);
                          }}
                          disabled={isSharing}
                          className="w-full px-4 py-2 flex items-center gap-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {isSharing ? (
                            <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                          ) : (
                            <Share2 className="w-4 h-4 text-blue-500" />
                          )}
                          <span>Compartir</span>
                        </button>
                      )}

                      {/* Toggle disponibilidad (solo dueño y solo para empleos) */}
                      {isOwner && !isNonJobPublication && (
                        <button
                          onClick={handleToggleAvailability}
                          disabled={isTogglingActive}
                          className="w-full px-4 py-2 flex items-center gap-3 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
                        >
                          {!localIsActive ? (
                            <CheckCircle className="w-4 h-4 text-emerald-600" />
                          ) : (
                            <XCircle className="w-4 h-4 text-gray-500" />
                          )}
                          <span>
                            {localIsActive ? "No disponible" : "Disponible"}
                          </span>
                        </button>
                      )}

                      <button
                        onClick={() => {
                          setShowActionsMenu(false);
                          if (!userId) {
                            setShareError(
                              "Debes iniciar sesión para reportar esta publicación.",
                            );
                            setShareLink("");
                            setHasCopiedShareLink(false);
                            setShowShareModal(true);
                            return;
                          }
                          setShowReportModal(true);
                        }}
                        className="w-full px-4 py-2 flex items-center gap-3 text-sm text-gray-700 hover:bg-gray-50"
                      >
                        <Flag className="w-4 h-4 text-orange-500" />
                        <span>Reportar</span>
                      </button>

                      {isOwner && (
                        <button
                          onClick={() => {
                            setShowActionsMenu(false);
                            setShowDeleteModal(true);
                          }}
                          className="w-full px-4 py-2 flex items-center gap-3 text-sm text-rose-600 hover:bg-rose-50"
                        >
                          <Trash2 className="w-4 h-4" />
                          <span>Eliminar</span>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Sección de Imagen - Altura flexible */}
            <div
              className="relative w-full flex-1 flex-shrink-1 z-0 "
              style={{
                backgroundColor: dominantColor,
                transition: "background-color 0.3s ease",
              }}
            >


              <div className="absolute inset-0">
                {job.images && job.images.length > 0 ? (
                  <Swiper
                    direction="horizontal"
                    spaceBetween={0}
                    slidesPerView={1}
                    initialSlide={hasMap ? 1 : 0}
                    pagination={
                      job.images.length > 1 && !isMapMode && swiperRef.current?.activeIndex !== 0
                        ? {
                          clickable: true,
                          dynamicBullets: false,
                        }
                        : false
                    }
                    modules={[Pagination]}
                    className="w-full h-full "
                    simulateTouch={true}
                    grabCursor={true}
                    nested={true}
                    allowTouchMove={true}
                    touchStartPreventDefault={false}
                    preventClicks={false}
                    onSwiper={(swiper) => {
                      swiperRef.current = swiper;
                      const isMapSlide = hasMap && swiper.activeIndex === 0;
                      swiper.allowTouchMove = !isMapSlide;
                      try {
                        /*            console.log("[job-card] Swiper init (images)", {
                                     jobId: job?.id,
                                     hasMap,
                                     activeIndex: swiper.activeIndex,
                                     allowTouchMove: swiper.allowTouchMove,
                                     expectedInitialSlide: hasMap ? 1 : 0,
                                   }); */
                      } catch { }
                    }}
                    onSlideChange={(swiper) => {
                      setActiveSlideIndex(swiper.activeIndex);

                      // Extraer color de la nueva imagen cuando cambia el slide
                      const activeSlide = swiper.slides[swiper.activeIndex];
                      const img = activeSlide?.querySelector("img");

                      // Si es el slide del mapa (índice 0 cuando hay coordenadas), usar gris
                      const isMapSlide = hasMap && swiper.activeIndex === 0;

                      if (isMapSlide) {
                        setDominantColor("rgb(209, 213, 219)"); // gray-300
                        if (onColorChange) {
                          onColorChange("rgb(209, 213, 219)");
                        }
                        // Deshabilitar swipe cuando estamos en el mapa
                        swiper.allowTouchMove = false;
                        try {
                          /*         console.log("[job-card] Swiper change (images): map slide active", {
                                    jobId: job?.id,
                                    activeIndex: swiper.activeIndex,
                                    hasMap,
                                  }); */
                        } catch { }
                      } else {
                        // Habilitar swipe cuando no estamos en el mapa
                        swiper.allowTouchMove = true;
                        if (img && img.complete) {
                          extractDominantColor(img, {
                            source: "swiper-change",
                            key: swiper.activeIndex,
                          });
                        }
                        try {
                          /*       console.log("[job-card] Swiper change (images): image slide", {
                                  jobId: job?.id,
                                  activeIndex: swiper.activeIndex,
                                  hasMap,
                                }); */
                        } catch { }
                      }
                    }}
                    enabled={true}
                  >
                    {hasMap && (
                      <SwiperSlide key="map">
                        <div className="relative w-full h-full">
                          {/* Fondo gris para el mapa */}
                          <div
                            className="absolute inset-0 w-full h-full bg-gray-200"
                          />
                          {activeSlideIndex === 0 && (
                            <JobMapView
                              job={{ ...job, ubication: normalizedUbication }}
                              onClose={() => {
                                const firstImageIndex = hasMap ? 1 : 0;
                                try {
                                  console.log('[job-card] Map onClose: sliding to', firstImageIndex, {
                                    jobId: job?.id,
                                  });
                                } catch { }
                                swiperRef.current?.slideTo(firstImageIndex);
                              }}
                            />
                          )}
                        </div>
                      </SwiperSlide>
                    )}
                    {job.images.map((imageUrl, index) => (
                      <SwiperSlide key={index}>
                        <PhotoView src={imageUrl}>
                          <div className="relative w-full h-full cursor-pointer">
                            {/* Fondo con color dominante */}
                            <div
                              className="absolute inset-0 w-full h-full"
                              style={{
                                backgroundColor: dominantColor,
                                transition: "background-color 0.3s ease",
                              }}
                            />
                            {/* Imagen principal */}
                            <img
                              src={imageUrl}
                              alt={`${job.title} - ${index + 1}`}
                              className={`relative w-full h-full object-contain z-0 transition-opacity duration-300 ${imageLoadState[index]
                                ? "opacity-100"
                                : "opacity-0"
                                }`}
                              crossOrigin="anonymous"
                              draggable={false}
                              loading="lazy"
                              decoding="async"
                              onLoad={(event) => {
                                const shouldUpdateColor =
                                  !swiperRef.current ||
                                  swiperRef.current.activeIndex === (hasMap ? index + 1 : index);
                                handleImageLoad(index, event, shouldUpdateColor);
                              }}
                              onError={(e) => {
                                e.target.src =
                                  'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"%3E%3Crect fill="%234299e1" width="400" height="400"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="60" fill="white"%3E📋%3C/text%3E%3C/svg%3E';
                              }}
                            />
                            {renderOwnerBadgeOverlay()}
                          </div>
                        </PhotoView>
                      </SwiperSlide>
                    ))}
                  </Swiper>
                ) : job.url ? (
                  <Swiper
                    direction="horizontal"
                    spaceBetween={0}
                    slidesPerView={1}
                    initialSlide={hasMap ? 1 : 0}
                    pagination={false}
                    modules={[Pagination]}
                    className="w-full h-full "
                    simulateTouch={true}
                    grabCursor={true}
                    nested={true}
                    allowTouchMove={true}
                    touchStartPreventDefault={false}
                    preventClicks={false}
                    onSwiper={(swiper) => {
                      swiperRef.current = swiper;
                      const isMapSlide = hasMap && swiper.activeIndex === 0;
                      swiper.allowTouchMove = !isMapSlide;
                      try {
                        /*          console.log("[job-card] Swiper init (single-url)", {
                                   jobId: job?.id,
                                   hasMap,
                                   activeIndex: swiper.activeIndex,
                                   allowTouchMove: swiper.allowTouchMove,
                                   expectedInitialSlide: hasMap ? 1 : 0,
                                 }); */
                      } catch { }
                    }}
                    onSlideChange={(swiper) => {
                      setActiveSlideIndex(swiper.activeIndex);

                      const isMapSlide = hasMap && swiper.activeIndex === 0;

                      if (isMapSlide) {
                        setDominantColor("rgb(209, 213, 219)"); // gray-300
                        if (onColorChange) {
                          onColorChange("rgb(209, 213, 219)");
                        }
                        swiper.allowTouchMove = false;
                        try {
                          /*            console.log("[job-card] Swiper change (single-url): map slide active", {
                                       jobId: job?.id,
                                       activeIndex: swiper.activeIndex,
                                       hasMap,
                                     }); */
                        } catch { }
                      } else {
                        swiper.allowTouchMove = true;
                        // Re-extraer color dominante de la imagen activa
                        const activeSlide = swiper.slides[swiper.activeIndex];
                        const img = activeSlide?.querySelector('img');
                        if (img && img.complete) {
                          extractDominantColor(img, { source: 'swiper-change-single-url', key: 'primary' });
                        }
                        try {
                          /*      console.log("[job-card] Swiper change (single-url): image slide", {
                                 jobId: job?.id,
                                 activeIndex: swiper.activeIndex,
                                 hasMap,
                               }); */
                        } catch { }
                      }
                    }}
                    enabled={true}
                  >
                    {hasMap && (
                      <SwiperSlide key="map">
                        <div className="relative w-full h-full">
                          <div className="absolute inset-0 w-full h-full bg-gray-200" />
                          {activeSlideIndex === 0 && (
                            <JobMapView
                              job={{ ...job, ubication: normalizedUbication }}
                              onClose={() => {
                                const firstImageIndex = hasMap ? 1 : 0;
                                swiperRef.current?.slideTo(firstImageIndex);
                              }}
                            />
                          )}
                        </div>
                      </SwiperSlide>
                    )}

                    <SwiperSlide key="single-image">
                      <PhotoView src={job.url}>
                        <div className="relative w-full h-full cursor-pointer">
                          <div
                            className="absolute inset-0 w-full h-full"
                            style={{
                              backgroundColor: dominantColor,
                              transition: "background-color 0.3s ease",
                            }}
                          />
                          <img
                            src={job.url}
                            alt={job.title || "Imagen del trabajo"}
                            className={`relative w-full h-full object-contain z-0 transition-opacity duration-300 ${imageLoadState.primary ? 'opacity-100' : 'opacity-0'}`}
                            crossOrigin="anonymous"
                            draggable={false}
                            loading="lazy"
                            decoding="async"
                            onLoad={(event) => {
                              const shouldUpdateColor =
                                !swiperRef.current ||
                                swiperRef.current.activeIndex === (hasMap ? 1 : 0);
                              handleImageLoad("primary", event, shouldUpdateColor);
                            }}
                            onError={(e) => {
                              e.target.src =
                                'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400"%3E%3Crect fill="%234299e1" width="400" height="400"/%3E%3Ctext x="50%25" y="50%25" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="60" fill="white"%3E📋%3C/text%3E%3C/svg%3E';
                            }}
                          />
                          {renderOwnerBadgeOverlay()}
                        </div>
                      </PhotoView>
                    </SwiperSlide>
                  </Swiper>
                ) : (
                  // Sin imágenes ni url: usamos Swiper con (opcional) mapa + flyer
                  <Swiper
                    direction="horizontal"
                    spaceBetween={0}
                    slidesPerView={1}
                    initialSlide={hasMap ? 1 : 0}
                    pagination={false}
                    modules={[Pagination]}
                    className="w-full h-full "
                    nested={true}
                    allowTouchMove={true}
                    touchStartPreventDefault={false}
                    preventClicks={false}
                    onSwiper={(swiper) => {
                      swiperRef.current = swiper;
                      const isMapSlide = hasMap && swiper.activeIndex === 0;
                      swiper.allowTouchMove = !isMapSlide;
                      try {
                        /* console.log("[job-card] Swiper init (flyer)", {
                          jobId: job?.id,
                          hasMap,
                          activeIndex: swiper.activeIndex,
                          allowTouchMove: swiper.allowTouchMove,
                          expectedInitialSlide: hasMap ? 1 : 0,
                          forceFlyer: job?.forceFlyer,
                        }); */
                      } catch { }
                    }}
                    onSlideChange={(swiper) => {
                      setActiveSlideIndex(swiper.activeIndex);

                      const isMapSlide = hasMap && swiper.activeIndex === 0;

                      if (isMapSlide) {
                        setDominantColor("rgb(209, 213, 219)"); // gray-300
                        if (onColorChange) {
                          onColorChange("rgb(209, 213, 219)");
                        }
                        // Deshabilitar swipe cuando estamos en el mapa
                        swiper.allowTouchMove = false;
                        try {
                          /*          console.log("[job-card] Swiper change (flyer): map slide active", {
                                     jobId: job?.id,
                                     activeIndex: swiper.activeIndex,
                                     hasMap,
                                   }); */
                        } catch { }
                      } else {
                        // Habilitar swipe cuando no estamos en el mapa
                        swiper.allowTouchMove = true;
                        // Al volver al flyer, reestablecer su color dominante
                        if (flyerColorRef.current) {
                          setDominantColor(flyerColorRef.current);
                          if (onColorChange) {
                            onColorChange(flyerColorRef.current);
                          }
                        }
                        try {
                          /*         console.log("[job-card] Swiper change (flyer): flyer slide", {
                                    jobId: job?.id,
                                    activeIndex: swiper.activeIndex,
                                    hasMap,
                                  }); */
                        } catch { }
                      }
                    }}
                    enabled={true}
                  >
                    {hasMap && (
                      <SwiperSlide key="map">
                        <div className="relative w-full h-full">
                          <div className="absolute inset-0 w-full h-full bg-gray-200" />
                          {activeSlideIndex === 0 && (
                            <JobMapView
                              job={{ ...job, ubication: normalizedUbication }}
                              onClose={() => {
                                const flyerIndex = hasMap ? 1 : 0;
                                swiperRef.current?.slideTo(flyerIndex);
                              }}
                            />
                          )}
                        </div>
                      </SwiperSlide>
                    )}

                    <SwiperSlide key="flyer">
                      <div className="relative w-full h-full flex justify-center items-center">
                        <div
                          className="absolute inset-0 w-full h-full"
                          style={{
                            backgroundColor: dominantColor,
                            transition: "background-color 0.3s ease",
                          }}
                        />
                        <FlyerView
                          job={job}
                          onColorChange={(color) => {
                            if (!color) {
                              console.warn("[job-card] FlyerView reported empty color", {
                                jobId: job?.id,
                              });
                              return;
                            }
                            if (color === dominantColor) {
                              console.debug(
                                "[job-card] FlyerView color matches current state, skipping persist",
                                {
                                  jobId: job?.id,
                                  color,
                                },
                              );
                              // aunque coincida, actualizamos la referencia para usarla al volver del mapa
                              flyerColorRef.current = color;
                              return;
                            }
                            console.debug("[job-card] FlyerView provided dominant color", {
                              jobId: job?.id,
                              color,
                            });
                            flyerColorRef.current = color;
                            setDominantColor(color);
                            persistDominantColor(color, "flyer");
                            if (onColorChange) {
                              onColorChange(color);
                            }
                          }}
                        />
                        {renderOwnerBadgeOverlay()}
                      </div>
                    </SwiperSlide>
                  </Swiper>
                )}
              </div>

              {hasMap && activeSlideIndex !== 0 && (
                <button
                  type="button"
                  onClick={goToMapSlide}
                  aria-label="Ver mapa"
                  className="absolute top-3 left-3 z-40 px-3 py-1.5 rounded-full bg-black/60 text-white text-xs font-medium flex items-center gap-1 backdrop-blur-sm active:scale-95 animate-bounce-in cursor-pointer"
                >
                  <ArrowLeft className="w-4 h-4" />
                  <span>Ver mapa</span>
                </button>
              )}

              {/* Modales - Posicionados sobre la imagen */}
              {activeModal === "map" && (
                <div className="absolute inset-0 z-900">
                  <JobMapView
                    job={{ ...job, ubication: normalizedUbication }}
                    onClose={() => setActiveModal("gallery")}
                  />
                </div>
              )}

              {activeModal === "contact" && (
                <div className="absolute inset-0 z-900">
                  <JobContactView
                    job={job}
                    onClose={() => setActiveModal("gallery")}
                  />
                </div>
              )}

              {activeModal === "details" && (
                <div className="absolute inset-0 z-900">
                  <JobDetailView
                    job={job}
                    onClose={() => setActiveModal("gallery")}
                  />
                </div>
              )}
            </div>

            {/* Sección de Información - Altura fija 25% */}
            <div
              className={`relative bottom-0 min-h-20 lg:pb-2 pb-2 gap-3 h-fit left-0 right-0 ${isInfoExpanded ? "max-h-[calc(100vh-8em)]" : ""} overflow-y-auto bg-white flex flex-col px-[1.05rem]  z-90  transition-all duration-300 ease-in-out `}
            >

              {/* Información del trabajo */}

              <div
                onClick={() => {
                  setShowMap(false);
                }}
                className="flex flex-col gap-1"
              >
                {/* Título - Lo más importante primero */}
                {job.title && (
                  <div className="flex flex-row w-full justify-between items-center gap-4">
                    <div
                      onClick={() => {
                        setIsInfoExpanded(!isInfoExpanded);
                        setActiveSection(isInfoExpanded ? null : "description");
                      }}
                      className="cursor-pointer mt-1"
                    >
                      <h3 className="font-bold uppercase text-gray-900 text-base">
                        {job.title}
                      </h3>

                    </div>
                    {/* Botón de favorito posicionado sobre la imagen */}
                    {!isRentPublication && (
                      <div className="relative z-50">
                        <button
                          onClick={handleSave}
                          className="w-10 h-10  rounded-lg flex items-center justify-center transition-all duration-200 active:scale-90"
                        >
                          <svg
                            aria-label="Guardar"
                            className={`x1lliihq x1n2onr6 xyb1xck ${actualIsSaved ? "text-black" : "text-black"} ${isAnimating ? "animate-shake-scale" : ""}`}
                            fill="none"
                            height="28"
                            role="img"
                            viewBox="0 0 24 24"
                            width="28"
                          >
                            <title>Guardar</title>
                            <polygon
                              fill={actualIsSaved ? "currentColor" : "none"}
                              points="20 21 12 13.44 4 21 4 3 20 3 20 21"
                              stroke="currentColor"
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth="1.5"
                            />
                          </svg>
                        </button>
                      </div>
                    )}

                  </div>


                )}

                {(categories.length > 0 || !isNonJobPublication) && (
                  <div className="flex flex-wrap items-center gap-2 ">

                    {!isNonJobPublication && (
                      <div className={`inline-flex items-center gap-1 w-fit px-3 py-1 ${availabilityBadge.classes} text-[0.75em] rounded-full`}>
                        {localIsActive ? (
                          <CheckCircle className="w-3 h-3" />
                        ) : (
                          <XCircle className="w-3 h-3" />
                        )}
                        <span>{availabilityBadge.label}</span>
                      </div>
                    )}
                    {categories.map((cat, index) => (
                      <div key={index} className="inline-block w-fit px-3 py-1 bg-blue-200 text-gray-700 text-[0.75em] rounded-full ">
                        {cat}
                      </div>
                    ))}
                  </div>
                )}

                {/* Descripción */}
                {job.description && (
                  <div className="text-gray-700 text-[14px] leading-5">
                    <Linkify
                      as="span"
                      className={`whitespace-pre-line transition-all duration-300 ease-in-out ${!isInfoExpanded ? "line-clamp-3" : ""} cursor-pointer`}
                      onClick={() => {
                        setIsInfoExpanded(!isInfoExpanded);
                        setActiveSection(isInfoExpanded ? null : "description");
                      }}
                      options={{
                        target: "_blank",
                        rel: "noopener noreferrer",
                        className: "text-blue-600 hover:text-blue-800 underline",
                      }}
                    >
                      {job.description}
                    </Linkify>
                  </div>
                )}

                {/* Ciudad (solo cuando no está expandido) */}
                {!isInfoExpanded && job.city && (
                  <div className="flex items-center gap-1 mt-2">
                    <MapPin
                      size={12}
                      strokeWidth={1.5}
                      className="text-gray-600"
                    />
                    <p className="text-gray-600 text-sm">
                      {job.departamento}{job.city && `, ${job.city}`}
                    </p>
                  </div>
                )}

                {/* Acordeones de información expandida */}
                {isInfoExpanded && (
                  <div className="mt-3 space-y-0 text-sm">
                    {/* Datos del puesto */}
                    <div className="border-b border-gray-200">
                      <button
                        onClick={() =>
                          setActiveSection(
                            activeSection === "datos" ? null : "datos",
                          )
                        }
                        className="w-full flex items-center justify-between py-2.5 hover:bg-gray-50 transition-colors duration-200"
                      >
                        <p className="font-bold text-gray-800">Datos</p>
                        <ChevronDown
                          size={16}
                          className={`text-gray-600 transition-transform duration-300 ease-in-out ${activeSection === "datos" ? "rotate-180" : ""}`}
                        />
                      </button>
                      <div
                        className={`overflow-hidden transition-all duration-300 ease-in-out ${activeSection === "datos" ? "max-h-96 opacity-100 pb-2.5" : "max-h-0 opacity-0"}`}
                      >
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-4 gap-y-1.5">
                          {job.company && (
                            <div className="flex items-start  gap-1">
                              <Building
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700 flex-shrink-0"
                              />
                              <p className="text-gray-700">
                                {job.company}
                              </p>
                            </div>
                          )}

                          {job.position && !isRentPublication && (
  <div className="flex items-start gap-1">
    <Briefcase
      size={12}
      strokeWidth={1.5}
      className="text-gray-700 flex-shrink-0"
    />
    <p className="text-gray-700">
      {job.position}
    </p>
  </div>
)}


                          {(job.vacancies > 0 && !isRentPublication) && (
                            <div className="flex items-start  gap-1">
                              <Users
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700 flex-shrink-0"
                              />
                              <p className="text-gray-700">
                                {job.vacancies}{" "}
                                {job.vacancies === 1 ? "vacante" : "vacantes"}
                              </p>
                            </div>
                          )}
                          {job.salary_range && (
                            <div className="flex items-start  gap-1">
                              <Banknote
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700 flex-shrink-0"
                              />
                              <p className="text-gray-700">
                                {job.salary_range}
                              </p>
                            </div>
                          )}
                          {console.log('DEBUG requeriments:', job.requeriments)}  {/* ← AGREGAR ESTO */}
                          {(job.requeriments && job.requeriments.length > 0) && (
                            <div className="flex items-start gap-1">
                              <FileText
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700 flex-shrink-0 mt-0.5"
                              />
                              <div className="text-gray-700 space-y-0.5">
                                {job.requeriments.map((req, index) => (
                                  <p key={index}>• {req}</p>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Ubicación */}
                    <div className="border-b border-gray-200">
                      <button
                        onClick={() =>
                          setActiveSection(
                            activeSection === "ubicacion" ? null : "ubicacion",
                          )
                        }
                        className="w-full flex items-center justify-between py-2.5 hover:bg-gray-50 transition-colors duration-200"
                      >
                        <p className="font-bold  text-gray-800">
                          Ubicación
                        </p>
                        <ChevronDown
                          size={16}
                          className={`text-gray-600 transition-transform duration-300 ease-in-out ${activeSection === "ubicacion" ? "rotate-180" : ""}`}
                        />
                      </button>
                      <div
                        className={`overflow-hidden transition-all duration-300 ease-in-out ${activeSection === "ubicacion" ? "max-h-96 opacity-100 pb-2.5" : "max-h-0 opacity-0"}`}
                      >
                        <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                          {(job.departamento || job.city) && (
                            <div className="flex items-start gap-1">
                              <MapPin
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700"
                              />
                              <p className="text-gray-700">
                                {[job.departamento, job.city].filter(Boolean).join(', ')}
                              </p>
                            </div>
                          )}
                          {job.direction && (
                            <div className="flex items-start gap-1">
                              <MapPinned
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700"
                              />
                              <p className="text-gray-700 ">
                                {job.direction}
                              </p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Contacto */}
                    <div className="border-b border-gray-200">
                      <button
                        onClick={() =>
                          setActiveSection(
                            activeSection === "contacto" ? null : "contacto",
                          )
                        }
                        className="w-full flex items-center justify-between py-2.5 hover:bg-gray-50 transition-colors duration-200"
                      >
                        <p className="font-bold text-gray-800">
                          Contacto
                        </p>
                        <ChevronDown
                          size={16}
                          className={`text-gray-600 transition-transform duration-300 ease-in-out ${activeSection === "contacto" ? "rotate-180" : ""}`}
                        />
                      </button>
                      <div
                        className={`overflow-hidden transition-all duration-300 ease-in-out ${activeSection === "contacto" ? "max-h-96 opacity-100 pb-2.5" : "max-h-0 opacity-0"}`}
                      >
                        <div className="grid grid-cols-1 gap-x-4 gap-y-1.5 mb-2.5">
                          {job.phoneNumber && (
                            <div className="flex items-start  gap-1">
                              <Phone
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700"
                              />
                              <p className="text-gray-700 ">
                                {job.phoneNumber}
                              </p>

                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(job.phoneNumber);
                                  setCopiedField("phone");
                                  setTimeout(() => setCopiedField(null), 2000);
                                }}
                                className="text-gray-600 hover:text-gray-800 transition-colors"
                                title="Copiar teléfono"
                              >
                                {copiedField === "phone" ? (
                                  <Check
                                    size={12}
                                    strokeWidth={1.5}
                                    className="text-green-600"
                                  />
                                ) : (
                                  <Copy size={12} strokeWidth={1.5} />
                                )}
                              </button>
                            </div>
                          )}
                          {job.email && (
                            <div className="flex items-start  gap-1">
                              <Mail
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700"
                              />
                              <p className="text-gray-700">{job.email}</p>
                              <button
                                onClick={() => {
                                  navigator.clipboard.writeText(job.email);
                                  setCopiedField("email");
                                  setTimeout(() => setCopiedField(null), 2000);
                                }}
                                className="text-gray-600 hover:text-gray-800 transition-colors"
                                title="Copiar email"
                              >
                                {copiedField === "email" ? (
                                  <Check
                                    size={12}
                                    strokeWidth={1.5}
                                    className="text-green-600"
                                  />
                                ) : (
                                  <Copy size={12} strokeWidth={1.5} />
                                )}
                              </button>
                            </div>
                          )}
                          {job.website && (
                            <div className="flex items-start  gap-1 col-span-2">
                              <Globe
                                size={12}
                                strokeWidth={1.5}
                                className="text-gray-700"
                              />
                              <a
                                href={
                                  job.website.startsWith("http")
                                    ? job.website
                                    : `https://${job.website}`
                                }
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 inline-flex items-center gap-1"
                              >
                                <span className="truncate">{job.website}</span>
                                <ExternalLink
                                  size={10}
                                  className="flex-shrink-0"
                                />
                              </a>
                            </div>
                          )}
                        </div>

                        {/* Botones de contacto */}
                        {(job.phoneNumber || job.email || job.website) && (
                          <div className="flex flex-row gap-2">
                            {job.phoneNumber && (
                              <a
                                href={whatsappHref || `https://api.whatsapp.com/send?phone=${cleanPhoneForWhatsApp(job.phoneNumber)}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="w-9 h-9 bg-emerald-600 hover:bg-emerald-700 text-white flex items-center justify-center rounded-full transition-all duration-200 hover:scale-105"
                              >
                                <svg
                                  xmlns="http://www.w3.org/2000/svg"
                                  fill="currentColor"
                                  viewBox="0 0 24 24"
                                  className="w-5 h-5"
                                >
                                  <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413Z" />
                                </svg>
                              </a>
                            )}
                            {job.email && (
                              <a
                                href={mailtoHref || `mailto:${job.email}`}
                                target="_blank" rel="noopener noreferrer"
                                className="w-9 h-9 bg-rose-400 hover:bg-rose-500 text-white flex items-center justify-center rounded-full transition-all duration-200 hover:scale-105"
                                aria-label="Enviar postulación por correo"
                              >
                                <Mail size={18} />


                              </a>
                            )}
                            {job.website && (
                              <a
                                href={
                                  job.website.startsWith("http")
                                    ? job.website
                                    : `https://${job.website}`
                                }
                                target="_blank"
                                rel="noopener noreferrer"
                                className="w-9 h-9 bg-cyan-600 hover:bg-cyan-700 text-white flex items-center justify-center rounded-full transition-all duration-200 hover:scale-105"
                              >
                                <Globe size={18} />
                              </a>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </PhotoProvider>
      </React.Suspense>

      {showShareModal &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center p-4">
            <div className="bg-white rounded-lg p-8 max-w-md w-full animate-fadeIn shadow-xl relative">
              <button
                onClick={handleCloseShareModal}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all"
              >
                <X className="w-5 h-5" />
              </button>

              {shareError ? (
                <div className="flex flex-col items-center text-center gap-4">
                  <div className="w-16 h-16 bg-rose-50 rounded-full flex items-center justify-center border border-rose-100">
                    <XCircle className="w-7 h-7 text-rose-500" />
                  </div>
                  <div>
                    <h3 className="text-2xl font-bold text-gray-900">
                      No se pudo crear el enlace
                    </h3>
                    <p className="text-gray-500 mt-2 text-sm">{shareError}</p>
                  </div>
                  <button
                    onClick={handleCloseShareModal}
                    className="w-full py-3 bg-rose-500 text-white rounded-lg font-semibold hover:bg-rose-600 transition-all shadow-md"
                  >
                    Cerrar
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-5">
                  <div className="flex flex-col items-center text-center gap-3">
                    <div className="w-16 h-16 bg-blue-50 rounded-full flex items-center justify-center border border-blue-100">
                      <Share2 className="w-7 h-7 text-blue-500" />
                    </div>
                    <div>
                      <h3 className="text-2xl font-bold text-gray-900">
                        Enlace listo para compartir
                      </h3>
                      <p className="text-gray-500 text-sm">
                        Envía este enlace para que puedan ver la publicación.
                      </p>
                    </div>
                  </div>

                  {shareLink && (
                    <div className="bg-gray-50 border border-gray-200 rounded-lg px-3 py-3 flex flex-col gap-2">
                      <div className="text-xs uppercase font-semibold text-gray-400 tracking-wide">
                        Enlace generado
                      </div>
                      <div className="flex items-center gap-3">
                        <input
                          type="text"
                          readOnly
                          value={shareLink}
                          className="flex-1 bg-transparent text-sm text-gray-700 font-medium truncate focus:outline-none"
                        />
                        <button
                          type="button"
                          onClick={handleCopyShareLink}
                          className="px-3 py-1 bg-blue-500 text-white text-sm font-semibold rounded-md hover:bg-blue-600 transition-colors"
                        >
                          {hasCopiedShareLink ? "Copiado" : "Copiar"}
                        </button>
                      </div>
                    </div>
                  )}

                  {hasCopiedShareLink && (
                    <p className="text-sm text-green-500 text-center">
                      Enlace copiado al portapapeles
                    </p>
                  )}

                  <button
                    onClick={handleCloseShareModal}
                    className="w-full py-3 bg-gray-900 text-white rounded-lg font-semibold hover:bg-black transition-all shadow-md"
                  >
                    Cerrar
                  </button>
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}

      {showReportModal &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center p-4">
            <div className="bg-white rounded-lg p-8 max-w-md w-full animate-fadeIn shadow-xl relative">
              <button
                onClick={handleReportModalClose}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center flex-col gap-3 mb-5 text-center">
                <div className="w-16 h-16 bg-orange-50 rounded-full flex items-center justify-center border border-orange-100">
                  <Flag className="w-7 h-7 text-orange-500" strokeWidth={2} />
                </div>
                <h3 className="text-2xl font-bold text-gray-900">
                  Reportar publicacion
                </h3>
                <p className="text-gray-500 text-sm">
                  Comparte mas detalles para que podamos revisar esta publicacion.
                </p>
              </div>

              <form onSubmit={handleReportSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    Motivo del reporte
                  </label>
                  <select
                    value={reportReason}
                    onChange={(event) => setReportReason(event.target.value)}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent text-sm"
                  >
                    <option value="">Selecciona una opcion</option>
                    <option value="spam">Spam o fraude</option>
                    <option value="datos_incorrectos">Datos incorrectos o enganosos</option>
                    <option value="contenido_inapropiado">Contenido inapropiado</option>
                    <option value="otro">Otro</option>
                  </select>
                </div>

                <div>
                  <label className="block text-sm font-semibold text-gray-700 mb-2">
                    Detalles adicionales
                  </label>
                  <textarea
                    value={reportDetails}
                    onChange={(event) => setReportDetails(event.target.value)}
                    rows={4}
                    placeholder="Describe lo que sucede o agrega enlaces relevantes."
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-orange-400 focus:border-transparent text-sm resize-none"
                  />
                </div>

                {reportError && (
                  <p className="text-sm text-red-500">{reportError}</p>
                )}

                <div className="flex gap-3 pt-2">

                  <button
                    type="submit"
                    disabled={isSubmittingReport}
                    className={`flex-1 py-3 bg-orange-500 text-white rounded-lg font-semibold transition-all shadow-md flex items-center justify-center gap-2 ${isSubmittingReport
                      ? "opacity-70 cursor-not-allowed"
                      : "hover:bg-orange-600"
                      }`}
                  >
                    {isSubmittingReport ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Enviando...
                      </>
                    ) : (
                      "Enviar reporte"
                    )}
                  </button>
                </div>
              </form>
            </div>
          </div>,
          document.body,
        )}

      {reportSubmitted &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[10000] flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center animate-fadeIn shadow-2xl">
              <CheckCircle className="w-16 h-16 text-orange-500 mx-auto mb-4" />
              <h3 className="text-2xl font-bold text-gray-800 mb-2">
                Reporte enviado
              </h3>
              <p className="text-gray-600 mb-6">
                Gracias por ayudarnos a mantener la comunidad segura.
              </p>
              <button
                onClick={handleCloseReportSuccess}
                className="w-full py-3 bg-orange-500 text-white rounded-lg font-semibold hover:bg-orange-600 transition-all"
              >
                Cerrar
              </button>
            </div>
          </div>,
          document.body,
        )}

      {showDisableModal &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center p-4">
            <div className="bg-white rounded-lg p-8 max-w-md w-full animate-fadeIn shadow-xl relative">
              <button
                onClick={() => setShowDisableModal(false)}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center flex-col gap-3 mb-5 text-center">
                <div className="w-16 h-16 bg-amber-50 rounded-full flex items-center justify-center border border-amber-100">
                  <Clock className="w-7 h-7 text-amber-500" />
                </div>
                <h3 className="text-2xl font-bold text-gray-900">
                  Deshabilitar disponibilidad
                </h3>
                <p className="text-gray-500 text-sm">
                  Esta publicación dejará de mostrarse en el feed. Podrás reactivarla cuando quieras.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowDisableModal(false)}
                  type="button"
                  className="flex-1 py-3 bg-gray-100 text-gray-800 rounded-lg font-semibold hover:bg-gray-200 transition-all"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleConfirmDisableAvailability}
                  disabled={isDisabling}
                  className="flex-1 py-3 bg-amber-500 text-white rounded-lg font-semibold hover:bg-amber-600 disabled:bg-amber-300 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 shadow-md"
                >
                  {isDisabling ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Deshabilitando...
                    </>
                  ) : (
                    "Deshabilitar"
                  )}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {showEnableModal &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center p-4">
            <div className="bg-white rounded-lg p-8 max-w-md w-full animate-fadeIn shadow-xl relative">
              <button
                onClick={() => setShowEnableModal(false)}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all"
              >
                <X className="w-5 h-5" />
              </button>

              <div className="flex items-center flex-col gap-3 mb-5 text-center">
                <div className="w-16 h-16 bg-emerald-50 rounded-full flex items-center justify-center border border-emerald-100">
                  <CheckCircle className="w-7 h-7 text-emerald-600" />
                </div>
                <h3 className="text-2xl font-bold text-gray-900">
                  Habilitar disponibilidad
                </h3>
                <p className="text-gray-500 text-sm">
                  Esta publicación volverá a mostrarse en el feed. Podrás desactivarla cuando quieras.
                </p>
              </div>

              <div className="flex gap-3">
                <button
                  onClick={() => setShowEnableModal(false)}
                  type="button"
                  className="flex-1 py-3 bg-gray-100 text-gray-800 rounded-lg font-semibold hover:bg-gray-200 transition-all"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleConfirmEnableAvailability}
                  disabled={isEnabling}
                  className="flex-1 py-3 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-700 disabled:bg-emerald-300 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 shadow-md"
                >
                  {isEnabling ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      Habilitando...
                    </>
                  ) : (
                    "Habilitar"
                  )}
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}

      {showDeleteModal &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[9999] flex items-center justify-center p-4">
            <div className="bg-white rounded-lg p-8 max-w-md w-full animate-fadeIn shadow-xl relative">
              {/* Botón X para cerrar */}
              <button
                onClick={() => setShowDeleteModal(false)}
                className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-full transition-all"
              >
                <X className="w-5 h-5" />
              </button>

              {/* Header */}
              <div className="flex items-center flex-col gap-3 mb-5">
                <div className="w-16 h-16 bg-rose-50 rounded-full flex items-center justify-center border border-rose-100">
                  <Trash2 className="w-7 h-7 text-rose-500" strokeWidth={2} />
                </div>
                <h3 className="text-2xl font-bold text-gray-900">
                  ¿Eliminar publicación?
                </h3>
              </div>

              {/* Contenido */}
              <p className="text-gray-500 mb-5 leading-relaxed">
                Esta acción es permanente. La publicación será eliminada de
                forma irreversible.
              </p>

              {/* Botón Confirmar */}
              <button
                onClick={handleDeleteJob}
                disabled={isDeleting}
                className="w-full py-3.5 bg-rose-500 text-white rounded-lg font-semibold hover:bg-rose-600 disabled:bg-rose-300 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-2 shadow-md"
              >
                {isDeleting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    Eliminando...
                  </>
                ) : (
                  "Eliminar"
                )}
              </button>
            </div>
          </div>,
          document.body,
        )}

      {deleteSuccess &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[10000] flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center animate-fadeIn shadow-2xl">
              <CheckCircle className="w-16 h-16 text-green-500 mx-auto mb-4" />
              <h3 className="text-2xl font-bold text-gray-800 mb-2">
                ¡Eliminado!
              </h3>
              <p className="text-gray-600">
                La publicación se ha eliminado exitosamente
              </p>
            </div>
          </div>,
          document.body,
        )}

      {deleteError &&
        createPortal(
          <div className="fixed inset-0 bg-black/50 z-[10000] flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl p-8 max-w-sm w-full text-center animate-fadeIn shadow-2xl">
              <XCircle className="w-16 h-16 text-red-500 mx-auto mb-4" />
              <h3 className="text-2xl font-bold text-gray-800 mb-2">Error</h3>
              <p className="text-gray-600">
                No se pudo eliminar la publicación. Por favor intenta de nuevo.
              </p>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
