export interface CreateProductReviewInput {
    productId: number;
    title: string;
    comment: string;
    rating: number;
    name: string;
    email: string;
    attachments?: string | null;
}

export interface ProductReviewResponse {
    createProductReview: {
        productReview?: {
            id: string;
            name: string;
            title: string;
            rating: number;
            comment: string;
            status: string;
        };
    };
}
