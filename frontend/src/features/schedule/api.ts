import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { ScheduleEvent } from "../../types/api";

type BulkResult = { event_ids: number[]; response_code: "COMING" | "MAYBE"; count: number };

export function useBulkEventResponse() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (eventIds: number[]) => (await api.post<BulkResult>("/schedule/events/respond-bulk", { event_ids: eventIds, response_code: "COMING" })).data,
    onSuccess: (result) => {
      const ids = new Set(result.event_ids);
      client.setQueriesData<ScheduleEvent[]>({ queryKey: ["schedule", "list"] }, (items) => items?.map((event) => ids.has(event.id) ? { ...event, my_response_code: result.response_code } : event));
      void client.invalidateQueries({ queryKey: ["schedule"] });
      void client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useScheduleEvent(eventId: number | null) {
  return useQuery({
    queryKey: ["schedule", "detail", eventId],
    queryFn: async ({ signal }) => (await api.get<ScheduleEvent>(`/schedule/events/${eventId}`, { signal })).data,
    enabled: eventId !== null,
    staleTime: 15_000,
  });
}
