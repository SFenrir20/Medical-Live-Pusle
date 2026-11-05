export type WidgetConfig = {
  title: string;
  subtitle: string;
  color: string;
  text_color: string;
  position: "left" | "right";
  whatsapp: string;
  instagram: string;
  messenger: string;
  whatsapp_enabled: boolean;
  instagram_enabled: boolean;
  messenger_enabled: boolean;
};
export type PresetKey = "welcome" | "lead" | "appointment" | "followup";
export type MessagePreset = {
  key: PresetKey;
  text: string;
  enabled: boolean;
  delay_minutes: number;
  flow_id?: number;
};
