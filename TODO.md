Video 1 - 10
{model1, model2, model3,...}
3C2 -> 3개
3 * 10 ==> 300 sample

Video 11-20
{model1, model2, model3,. model4}
4C2 -> 6개
6 * 10 ==> 600 sample
900 sample + 300 (vidmuse 제외)
------------------------------------------------------------------------------------------------------------------------------------
User 30 x 40 question => 1200
User1 -> 40 assign (video 20 개를 최소 한번은 보기)
User2 -> 40 assign (video 20 개를 최소 한번은 보기)
..
User30 -> 40 assign (video 20 개를 최소 한번은 보기)

Minhee)
User1, ... 가 동시에 접근할수도 있으니까, 일단은 user id를 받은 다음에
그것들을 모두 assign 하는데 중복 없이 되도록 해야 함.
입력한 id랑 user id를 매핑하는 걸, test 시작할 때 일단 해줘야 할듯.
그리고 중간에 나가서 완료가 안되면, 그건 그 나름대로 핸들하고....