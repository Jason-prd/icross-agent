/** Shared API data-fetching hooks wrapping TanStack Query with consistent error handling. */
import { useQuery, UseQueryOptions } from '@tanstack/react-query'
import client from '../api/client'

type ApiQueryKey = readonly unknown[]

/** Fetch data with GET, auto-error-toast. */
export function useApiGet<TData = unknown>(
  queryKey: ApiQueryKey,
  url: string,
  params?: Record<string, unknown>,
  options?: Omit<UseQueryOptions<TData>, 'queryKey' | 'queryFn'>,
) {
  return useQuery<TData>({
    queryKey,
    queryFn: async () => {
      const { data } = await client.get(url, { params })
      return data as TData
    },
    ...options,
  })
}
