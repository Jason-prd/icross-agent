/** Shop management API functions. */
import client from './client'

export interface Shop {
  shop_id: string
  name: string
  client_id?: string
  status: string
  sync_days?: number
  last_auth_check?: string
  created_at?: string
  updated_at?: string
}

export interface ShopCreatePayload {
  shop_id: string
  name?: string
  client_id?: string
  api_key?: string
  token?: string
  sync_days?: number
}

export async function listShops(): Promise<Shop[]> {
  const res = await client.get('/api/shops')
  return res.data.shops ?? []
}

export async function createShop(data: ShopCreatePayload): Promise<Shop> {
  const res = await client.post('/api/shops', data)
  return res.data.shop
}

export async function authenticateShop(shopId: string): Promise<boolean> {
  try {
    await client.post(`/api/shops/${shopId}/authenticate`)
    return true
  } catch {
    return false
  }
}
