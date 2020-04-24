package com.herim.kh.dao;

import java.time.LocalDateTime;
import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;

import com.herim.kh.domain.Assessment;
import com.herim.kh.domain.User;

public interface AssessmentRepository extends JpaRepository<Assessment, String> {
	
	List<Assessment> findByAssesser(User user);
	
	@Query(value = "select * from assessment t where t.assesser_id = ?1 and t.type like ?2%",nativeQuery = true) 
	List<Assessment> findByUserAndType(String id, String type);
	
	@Query(value = "update assessment set score = ?1,finish_date = ?2 where id= ?3 ", nativeQuery = true) 
	@Modifying  
	public void updateScoreAndFinshDate(Integer score, LocalDateTime finishDate, String id);
	
	
	/*
	 *  create view user_score as select tt.user_id as userid,sum(tt.final_score) as finalscore from (
select aa.user_id ,(dd.dept_score*aa.weight_dept+aa.user_score) as final_score from
(select d.id as dept_id, d.score as dept_score from dept as d) as dd
inner join
(
select t.user_id,t.user_dept_id,t.weight_dept,sum(t.user_score) as user_score 
from(
select a.user_id,a.weight_dept,a.user_dept_id,avg(((a.score-1) *10 + 65 )*a.weight) as user_score from assessment a  group by a.user_id,a.type ,a.weight_dept,a.user_dept_id
) as t group by t.user_id,t.weight_dept
) as aa where dd.dept_id=aa.user_dept_id
) as tt group by tt.user_id
	 */
	
	
	@Query(value = "SELECT userid, finalscore FROM user_score order by finalscore desc", nativeQuery = true)
    List<NameOnly> calculateScore();

	   public static interface NameOnly {
		   
	     String getUserid();
	
	     Double getFinalscore();
	     
	
	  }
	   
}
