import { http, HttpResponse } from 'msw';

export const handlers = [
  // Intercept GET /api/v1/menu
  http.get('/api/v1/menu', () => {
    return HttpResponse.json({
      success: true,
      data: {
        categories: [{ id: '1', name: 'Drinks', sortOrder: 1 }],
        items: [
          {
            id: '1',
            categoryId: '1',
            name: 'Cola',
            price: 15.0,
            imageUrl: '',
            outOfStock: false
          }
        ]
      }
    });
  }),
];
