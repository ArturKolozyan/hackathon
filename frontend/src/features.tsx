import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, type Features } from "./api";
import { useFresh } from "./fresh";

const empty: Features & { loaded: boolean } = {
  assistant: false,
  assistant_available: false,
  voice: false,
  email: false,
  telegram: false,
  bot_alive: false,
  loaded: false,
};

const FeaturesContext = createContext(empty);

export function FeaturesProvider({ children }: { children: ReactNode }) {
  const [features, setFeatures] = useState(empty);
  const fresh = useFresh();
  useEffect(() => {
    api<Features>("/api/v1/features")
      .then((body) => setFeatures({ ...body, loaded: true }))
      .catch(() => setFeatures((current) => (current.loaded ? current : { ...empty, loaded: true })));
  }, [fresh]);
  return <FeaturesContext.Provider value={features}>{children}</FeaturesContext.Provider>;
}

export function useFeatures() {
  return useContext(FeaturesContext);
}
