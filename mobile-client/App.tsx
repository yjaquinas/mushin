/**
 * Mushin mobile shell — a thin Hyperview client.
 *
 * It renders server-driven HXML screens from the FastAPI backend's /m/ routes.
 * No screen-level logic lives here: navigation, forms, and state are all driven
 * by the server. See app/templates/mobile/ and the hyperview-patterns skill.
 */
import React from "react";
import Hyperview from "hyperview";

// Point at the backend's mobile entry screen.
// Dev: your machine's LAN IP + :8000. Prod: https://mushin.aqnas.xyz
const ENTRY_POINT_URL =
  process.env.EXPO_PUBLIC_ENTRY_URL ?? "http://127.0.0.1:8000/m/";

const fetchWrapper = (input: RequestInfo, init?: RequestInit) =>
  fetch(input, init);

export default function App() {
  return (
    <Hyperview
      entrypointUrl={ENTRY_POINT_URL}
      fetch={fetchWrapper}
      formatDate={(date: Date | null, format?: string) =>
        date ? date.toLocaleDateString() : ""
      }
    />
  );
}
