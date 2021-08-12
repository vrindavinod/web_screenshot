(function($) {
"use strict";

//     $('#toggle').on('click', function() {
//         $('.left-sidebar').toggleClass('show');
//    });

    $('.card-slider').slick({
        slidesToShow: 2,
        slidesToScroll: 1,
        autoplay: true,
        autoplaySpeed: 2000,
        arrows: false,
        loop: true,
        responsive: [
            {
            breakpoint: 1200,
            settings: {
            slidesToShow: 2,
            slidesToScroll: 1,
            arrows:false,
            }
        },
        {
            breakpoint: 992,
            settings: {
            slidesToShow: 2,
            slidesToScroll: 1
            }
        },
        {
            breakpoint: 767,
            settings: {
            slidesToShow:1,
            slidesToScroll: 1,
            arrows: false,
            }
        },
        {
            breakpoint: 500,
            settings: {
            slidesToShow: 1,
            slidesToScroll: 1,
            arrows: false,
            }
        }
        ]
    });


    $('.card-slider-two').slick({
        slidesToShow: 3,
        slidesToScroll: 1,
        autoplay: true,
        autoplaySpeed: 2000,
        arrows: false,
        loop: true,
        responsive: [
            {
            breakpoint: 1200,
            settings: {
            slidesToShow: 3,
            slidesToScroll: 1,
            arrows:false,
            }
        },
        {
            breakpoint: 992,
            settings: {
            slidesToShow: 2,
            slidesToScroll: 1
            }
        },
        {
            breakpoint: 767,
            settings: {
            slidesToShow:1,
            slidesToScroll: 1,
            arrows: false,
            }
        },
        {
            breakpoint: 500,
            settings: {
            slidesToShow: 1,
            slidesToScroll: 1,
            arrows: false,
            }
        }
        ]
    });

    $('.transfer-active').slick({
        slidesToShow: 3,
        slidesToScroll: 1,
        autoplay: true,
        autoplaySpeed: 2000,
        arrows: true,
        loop: true,
        prevArrow: '<button type="button" class="slick-prev"><i class="fas fa-chevron-left"></i></button>' ,
        nextArrow: '<button type="button" class="slick-next"><i class="fas fa-chevron-right"></i></button>' ,
        responsive: [
            {
            breakpoint: 1200,
            settings: {
            slidesToShow: 3,
            slidesToScroll: 1,
            arrows:false,
            }
        },
        {
            breakpoint: 992,
            settings: {
            slidesToShow: 3,
            slidesToScroll: 1
            }
        },
        {
            breakpoint: 767,
            settings: {
            slidesToShow:3,
            slidesToScroll: 1,
            arrows: false,
            }
        },
        {
            breakpoint: 500,
            settings: {
            slidesToShow: 2,
            slidesToScroll: 1,
            arrows: false,
            }
        }
        ]
    });


    $('#toggle').on('click', function() {
        $('.left-sidebar').toggleClass('show');
   });

       


})(jQuery);