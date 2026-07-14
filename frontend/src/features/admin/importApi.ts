import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { queryKeys } from "../../shared/api/queryKeys";
import type { ImportPreview } from "../../types/api";

export function useAdminImportPreview() {
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("upload", file);
      return (await api.post<ImportPreview>("/admin/imports/preview", form)).data;
    },
  });
}

export function useAdminImportCommit() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (previewId: string) => (
      await api.post<{ created: number; updated: number; audit_batch_id: number }>(
        `/admin/imports/${previewId}/commit`,
      )
    ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users });
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.audit });
    },
  });
}

export function useAdminAuditUndo() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (auditId: number) => (
      await api.post<{ audit_id: number; undo_audit_id: number; affected: number; detail: string }>(
        `/admin/audit/${auditId}/undo`,
      )
    ).data,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.users });
      queryClient.invalidateQueries({ queryKey: queryKeys.admin.audit });
    },
  });
}
