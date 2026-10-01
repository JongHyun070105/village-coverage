"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { CircleHelp, MapPin } from "lucide-react";
import type { Area, ScenarioResult } from "@/lib/types";

type Props = { areas: Area[]; result: ScenarioResult; activeArea?: string | null; onSelect?: (id: string) => void };
type KakaoMapStatus = "MISSING_KEY" | "LOADING" | "SCRIPT_FAILED" | "SDK_UNAVAILABLE" | "AUTH_OR_DOMAIN_ERROR" | "INITIALIZED";
type Overlay = { setMap: (map: unknown | null) => void };

type KakaoMaps = {
  load: (callback: () => void) => void;
  LatLng: new (latitude: number, longitude: number) => unknown;
  Map: new (container: HTMLElement, options: { center: unknown; level: number }) => unknown;
  CustomOverlay: new (options: { map: unknown; position: unknown; content: HTMLElement; yAnchor: number }) => Overlay;
};

declare global {
  interface Window { kakao?: { maps?: KakaoMaps } }
}

function statusFor(area: Area, result: ScenarioResult) {
  const assignment = result.assignments.find((item) => item.area_id === area.id);
  return {
    assignment,
    survey: area.needs_survey,
    label: area.needs_survey ? "조사 필요" : assignment?.status || "미충족",
    className: area.needs_survey ? "survey" : assignment?.status === "충족" ? "covered" : assignment?.status === "부분충족" ? "partial" : "uncovered",
  };
}

function statusMessage(status: KakaoMapStatus) {
  switch (status) {
    case "MISSING_KEY": return "NEXT_PUBLIC_KAKAO_MAP_JS_KEY가 빌드 또는 실행 환경에 없습니다.";
    case "LOADING": return "카카오 지도 SDK와 지도 인스턴스를 기다리는 중입니다.";
    case "SCRIPT_FAILED": return "SDK 요청에 실패했습니다. 네트워크 차단, 앱 키 인증, 허용 도메인을 확인하세요.";
    case "SDK_UNAVAILABLE": return "스크립트 뒤 지도 API를 찾지 못했습니다. JavaScript 키와 허용 도메인, 브라우저 콘솔을 확인하세요.";
    case "AUTH_OR_DOMAIN_ERROR": return "지도 인증 또는 도메인 오류 가능성이 있습니다. JavaScript SDK 도메인과 브라우저 콘솔을 확인하세요.";
    case "INITIALIZED": return "실제 Kakao 지도 인스턴스가 생성되었습니다. 권역 오버레이 개수도 아래에서 확인하세요.";
  }
}

export function CoverageMap({ areas, result, activeArea, onSelect }: Props) {
  const regionLabel = areas[0]?.town || "선택한 지역";
  const container = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<unknown>(null);
  const overlays = useRef<Overlay[]>([]);
  const [kakaoStatus, setKakaoStatus] = useState<KakaoMapStatus>(
    process.env.NEXT_PUBLIC_KAKAO_MAP_JS_KEY ? "LOADING" : "MISSING_KEY",
  );
  const [diagnostic, setDiagnostic] = useState({
    scriptLoaded: false,
    sdkAvailable: false,
    loadCallbackCalled: false,
    mapCreated: false,
    overlayCount: 0,
  });
  const mapKey = process.env.NEXT_PUBLIC_KAKAO_MAP_JS_KEY;
  const mapCenter = useMemo(() => ({
    latitude: areas.reduce((sum, area) => sum + area.anchor_lat, 0) / areas.length,
    longitude: areas.reduce((sum, area) => sum + area.anchor_lng, 0) / areas.length,
  }), [areas]);
  const bounds = useMemo(() => {
    const lats = areas.map((area) => area.anchor_lat);
    const lngs = areas.map((area) => area.anchor_lng);
    return {
      minLat: Math.min(...lats), maxLat: Math.max(...lats),
      minLng: Math.min(...lngs), maxLng: Math.max(...lngs),
    };
  }, [areas]);

  useEffect(() => {
    if (!mapKey) return;
    if (!container.current) return;

    let cancelled = false;
    let scriptTimer = 0;
    let callbackTimer = 0;
    let attachedScript: HTMLScriptElement | null = null;
    const clearTimers = () => {
      window.clearTimeout(scriptTimer);
      window.clearTimeout(callbackTimer);
    };
    const fail = (status: Exclude<KakaoMapStatus, "LOADING" | "INITIALIZED" | "MISSING_KEY">) => {
      if (cancelled) return;
      clearTimers();
      setKakaoStatus(status);
    };
    const initialize = () => {
      if (cancelled) return;
      window.clearTimeout(scriptTimer);
      if (attachedScript) attachedScript.dataset.kakaoLoadState = "loaded";
      const maps = window.kakao?.maps;
      if (!maps || typeof maps.load !== "function") {
        setDiagnostic((current) => ({ ...current, scriptLoaded: true }));
        fail("AUTH_OR_DOMAIN_ERROR");
        return;
      }
      setDiagnostic((current) => ({ ...current, scriptLoaded: true, sdkAvailable: true }));
      callbackTimer = window.setTimeout(() => fail("AUTH_OR_DOMAIN_ERROR"), 10_000);
      try {
        maps.load(() => {
          if (cancelled) return;
          window.clearTimeout(callbackTimer);
          setDiagnostic((current) => ({ ...current, loadCallbackCalled: true }));
          try {
            if (!container.current) return;
            const center = new maps.LatLng(mapCenter.latitude, mapCenter.longitude);
            mapInstance.current = new maps.Map(container.current, { center, level: 9 });
            setDiagnostic((current) => ({ ...current, mapCreated: true }));
            setKakaoStatus("INITIALIZED");
          } catch {
            fail("SDK_UNAVAILABLE");
          }
        });
      } catch {
        fail("AUTH_OR_DOMAIN_ERROR");
      }
    };
    const scriptFailed = () => fail("SCRIPT_FAILED");

    setKakaoStatus("LOADING");
    setDiagnostic({ scriptLoaded: false, sdkAvailable: false, loadCallbackCalled: false, mapCreated: false, overlayCount: 0 });
    const scriptId = "village-coverage-kakao-map";
    attachedScript = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (!attachedScript) {
      attachedScript = document.createElement("script");
      attachedScript.id = scriptId;
      attachedScript.async = true;
      attachedScript.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(mapKey)}&autoload=false`;
    }
    attachedScript.addEventListener("load", initialize, { once: true });
    attachedScript.addEventListener("error", scriptFailed, { once: true });
    scriptTimer = window.setTimeout(() => fail("SCRIPT_FAILED"), 15_000);
    if (window.kakao?.maps || attachedScript.dataset.kakaoLoadState === "loaded") initialize();
    else if (!attachedScript.isConnected) document.head.appendChild(attachedScript);

    return () => {
      cancelled = true;
      clearTimers();
      attachedScript?.removeEventListener("load", initialize);
      attachedScript?.removeEventListener("error", scriptFailed);
      overlays.current.forEach((overlay) => overlay.setMap(null));
      overlays.current = [];
      mapInstance.current = null;
    };
  }, [mapCenter.latitude, mapCenter.longitude, mapKey]);

  useEffect(() => {
    const maps = window.kakao?.maps;
    const map = mapInstance.current;
    if (kakaoStatus !== "INITIALIZED" || !maps || !map) return;

    overlays.current.forEach((overlay) => overlay.setMap(null));
    overlays.current = areas.map((area) => {
      const state = statusFor(area, result);
      const marker = document.createElement("button");
      marker.type = "button";
      marker.className = `map-pin ${state.className} ${activeArea === area.id ? "selected" : ""}`;
      marker.setAttribute("aria-label", `${area.name}, ${state.label}`);
      marker.innerHTML = `<span>${area.needs_survey ? "?" : state.assignment?.covered ? "✓" : "!"}</span><em>${area.village_name}</em>`;
      marker.addEventListener("click", () => onSelect?.(area.id));
      return new maps.CustomOverlay({
        map,
        position: new maps.LatLng(area.anchor_lat, area.anchor_lng),
        content: marker,
        yAnchor: 1,
      });
    });
    setDiagnostic((current) => ({ ...current, overlayCount: overlays.current.length }));
  }, [activeArea, areas, kakaoStatus, onSelect, result]);

  const fallbackVisible = kakaoStatus !== "INITIALIZED";
  const developmentDiagnostics = process.env.NODE_ENV !== "production";
  return (
    <div
      className="map-shell"
      data-testid={developmentDiagnostics ? "kakao-map-diagnostic" : undefined}
      data-kakao-status={developmentDiagnostics ? kakaoStatus : undefined}
      data-sdk-script-loaded={developmentDiagnostics ? diagnostic.scriptLoaded : undefined}
      data-sdk-available={developmentDiagnostics ? diagnostic.sdkAvailable : undefined}
      data-load-callback-called={developmentDiagnostics ? diagnostic.loadCallbackCalled : undefined}
      data-map-created={developmentDiagnostics ? diagnostic.mapCreated : undefined}
      data-overlay-count={developmentDiagnostics ? diagnostic.overlayCount : undefined}
    >
      <div className={`map-canvas ${kakaoStatus === "INITIALIZED" ? "kakao-active" : ""}`} ref={container} aria-label={`${regionLabel} 서비스 권역 지도`}>
        {fallbackVisible && areas.map((area) => {
          const state = statusFor(area, result);
          const latRange = Math.max(bounds.maxLat - bounds.minLat, 0.001);
          const lngRange = Math.max(bounds.maxLng - bounds.minLng, 0.001);
          const left = 10 + ((area.anchor_lng - bounds.minLng) / lngRange) * 80;
          const top = 12 + (1 - (area.anchor_lat - bounds.minLat) / latRange) * 72;
          return (
            <Link
              href={`/villages/${area.id}`}
              key={area.id}
              className={`map-pin ${state.className} ${activeArea === area.id ? "selected" : ""}`}
              style={{ left: `${left}%`, top: `${top}%` }}
              aria-label={`${area.name}, ${state.label}`}
              onClick={(event) => { if (onSelect) { event.preventDefault(); onSelect(area.id); } }}
            >
              <span>{area.needs_survey ? "?" : state.assignment?.covered ? "✓" : "!"}</span>
              <em>{area.village_name}</em>
            </Link>
          );
        })}
        {fallbackVisible && <div className="map-note"><MapPin size={15} /> 좌표 권역도 · Kakao 지도 {kakaoStatus}</div>}
        {kakaoStatus === "INITIALIZED" && <div className="map-note"><MapPin size={15} /> 시설 앵커 좌표 · 법정리 권역</div>}
      </div>
      <div className="map-legend" aria-label="지도 범례">
        <span><i className="legend-dot covered">✓</i> 충족</span>
        <span><i className="legend-dot partial">◐</i> 부분충족</span>
        <span><i className="legend-dot uncovered">!</i> 미충족</span>
        <span><i className="legend-dot survey">?</i> 조사 필요</span>
      </div>
      <div className="map-caption"><CircleHelp size={14} /> 지도 상태는 현재 선택한 시나리오의 월간 서비스 계획입니다.</div>
      {developmentDiagnostics && <p className="map-diagnostic" role="status" aria-live="polite">
        <strong>KAKAO_MAP_STATUS={kakaoStatus}</strong>
        <span>{statusMessage(kakaoStatus)}</span>
        <span>스크립트 {diagnostic.scriptLoaded ? "완료" : "대기"} · maps API {diagnostic.sdkAvailable ? "완료" : "대기"} · load 콜백 {diagnostic.loadCallbackCalled ? "완료" : "대기"} · 지도 인스턴스 {diagnostic.mapCreated ? "완료" : "대기"} · 권역 오버레이 {diagnostic.overlayCount}/{areas.length}</span>
      </p>}
    </div>
  );
}
