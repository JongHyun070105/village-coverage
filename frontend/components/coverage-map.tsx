"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { CircleHelp, MapPin } from "lucide-react";
import type { Area, ScenarioResult } from "@/lib/types";

type Props = { areas: Area[]; result: ScenarioResult; activeArea?: string | null; onSelect?: (id: string) => void };

type KakaoMaps = {
  load: (callback: () => void) => void;
  LatLng: new (latitude: number, longitude: number) => unknown;
  Map: new (container: HTMLElement, options: { center: unknown; level: number }) => unknown;
  CustomOverlay: new (options: { map: unknown; position: unknown; content: HTMLElement; yAnchor: number }) => unknown;
};

declare global {
  interface Window { kakao?: { maps: KakaoMaps } }
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

export function CoverageMap({ areas, result, activeArea, onSelect }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const [kakaoReady, setKakaoReady] = useState(false);
  const [kakaoFailed, setKakaoFailed] = useState(false);
  const mapKey = process.env.NEXT_PUBLIC_KAKAO_MAP_JS_KEY;
  const bounds = useMemo(() => {
    const lats = areas.map((area) => area.anchor_lat);
    const lngs = areas.map((area) => area.anchor_lng);
    return {
      minLat: Math.min(...lats), maxLat: Math.max(...lats),
      minLng: Math.min(...lngs), maxLng: Math.max(...lngs),
    };
  }, [areas]);

  useEffect(() => {
    if (!mapKey || !container.current) return;
    const init = () => {
      if (!window.kakao?.maps || !container.current) return;
      window.kakao.maps.load(() => {
        if (!container.current || !window.kakao?.maps) return;
        const kakao = window.kakao;
        const center = new kakao.maps.LatLng(
          areas.reduce((sum, area) => sum + area.anchor_lat, 0) / areas.length,
          areas.reduce((sum, area) => sum + area.anchor_lng, 0) / areas.length,
        );
        const map = new kakao.maps.Map(container.current, { center, level: 9 });
        for (const area of areas) {
          const state = statusFor(area, result);
          const marker = document.createElement("button");
          marker.type = "button";
          marker.className = `map-pin ${state.className} ${activeArea === area.id ? "selected" : ""}`;
          marker.setAttribute("aria-label", `${area.name}, ${state.label}`);
          marker.innerHTML = `<span>${area.needs_survey ? "?" : state.assignment?.covered ? "✓" : "!"}</span>`;
          marker.addEventListener("click", () => onSelect?.(area.id));
          new kakao.maps.CustomOverlay({
            map,
            position: new kakao.maps.LatLng(area.anchor_lat, area.anchor_lng),
            content: marker,
            yAnchor: 1,
          });
        }
        setKakaoReady(true);
      });
    };
    const scriptId = "village-coverage-kakao-map";
    let script = document.getElementById(scriptId) as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement("script");
      script.id = scriptId;
      script.async = true;
      script.src = `https://dapi.kakao.com/v2/maps/sdk.js?appkey=${encodeURIComponent(mapKey)}&autoload=false`;
      script.onload = init;
      script.onerror = () => setKakaoFailed(true);
      document.head.appendChild(script);
    } else if (window.kakao?.maps) {
      init();
    } else {
      script.addEventListener("load", init, { once: true });
    }
  }, [activeArea, areas, mapKey, onSelect, result]);

  return (
    <div className="map-shell">
      <div className={`map-canvas ${kakaoReady ? "kakao-active" : ""}`} ref={container} aria-label="장곡면 서비스 권역 지도">
        {(!mapKey || kakaoFailed) && areas.map((area) => {
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
        {!kakaoReady && !mapKey && <div className="map-note"><MapPin size={15} /> 좌표 기반 권역도 · 지도 키 미설정</div>}
        {!kakaoReady && mapKey && kakaoFailed && <div className="map-note"><MapPin size={15} /> Kakao 지도를 불러오지 못해 좌표 권역도를 표시합니다.</div>}
        {kakaoReady && <div className="map-note"><MapPin size={15} /> 시설 앵커 좌표 · 법정리 권역</div>}
      </div>
      <div className="map-legend" aria-label="지도 범례">
        <span><i className="legend-dot covered">✓</i> 충족</span>
        <span><i className="legend-dot partial">◐</i> 부분충족</span>
        <span><i className="legend-dot uncovered">!</i> 미충족</span>
        <span><i className="legend-dot survey">?</i> 조사 필요</span>
      </div>
      <div className="map-caption"><CircleHelp size={14} /> 지도 상태는 현재 선택한 시나리오의 월간 서비스 계획입니다.</div>
    </div>
  );
}
