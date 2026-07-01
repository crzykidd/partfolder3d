/**
 * Tests for carousel-utils.ts — pager math for the image carousel jump nav.
 */

import { describe, it, expect } from 'vitest'
import { buildCarouselPagerItems } from '@/lib/carousel-utils'

describe('buildCarouselPagerItems', () => {
  it('returns empty when totalPages is 0 or 1', () => {
    expect(buildCarouselPagerItems(0, 0)).toEqual([])
    expect(buildCarouselPagerItems(0, 1)).toEqual([])
  })

  it('returns all page indices when totalPages <= 7', () => {
    expect(buildCarouselPagerItems(0, 2)).toEqual([0, 1])
    expect(buildCarouselPagerItems(1, 3)).toEqual([0, 1, 2])
    expect(buildCarouselPagerItems(2, 5)).toEqual([0, 1, 2, 3, 4])
    expect(buildCarouselPagerItems(3, 7)).toEqual([0, 1, 2, 3, 4, 5, 6])
  })

  it('shows trailing ellipsis on first page of large set', () => {
    // currentPage=0, totalPages=10
    // left=max(1,-1)=1, right=min(8,1)=1
    // → [0, 1, ellipsis, 9]
    expect(buildCarouselPagerItems(0, 10)).toEqual([0, 1, 'ellipsis', 9])
  })

  it('shows both ellipses in the middle of a large set', () => {
    // currentPage=5, totalPages=10
    // left=max(1,4)=4, right=min(8,6)=6
    // → [0, ellipsis, 4, 5, 6, ellipsis, 9]
    expect(buildCarouselPagerItems(5, 10)).toEqual([0, 'ellipsis', 4, 5, 6, 'ellipsis', 9])
  })

  it('shows leading ellipsis on last page of large set', () => {
    // currentPage=9, totalPages=10
    // left=max(1,8)=8, right=min(8,10)=8
    // → [0, ellipsis, 8, 9]
    expect(buildCarouselPagerItems(9, 10)).toEqual([0, 'ellipsis', 8, 9])
  })

  it('handles page near the start without leading ellipsis', () => {
    // currentPage=1, totalPages=10
    // left=max(1,0)=1, right=min(8,2)=2
    // left > 1? No → no leading ellipsis
    // → [0, 1, 2, ellipsis, 9]
    expect(buildCarouselPagerItems(1, 10)).toEqual([0, 1, 2, 'ellipsis', 9])
  })

  it('handles page near the end without trailing ellipsis', () => {
    // currentPage=8, totalPages=10
    // left=max(1,7)=7, right=min(8,9)=8
    // right < totalPages-2? 8 < 8? No → no trailing ellipsis
    // → [0, ellipsis, 7, 8, 9]
    expect(buildCarouselPagerItems(8, 10)).toEqual([0, 'ellipsis', 7, 8, 9])
  })
})
