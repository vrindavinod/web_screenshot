from flask import Flask, jsonify, request, abort,render_template, make_response
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
import numpy as np
import matplotlib as mpl
import matplotlib.pyplot as plt
import os
import pdfkit
os.getcwd()
import gspread

app = Flask(__name__)
app.config['PDF_FOLDER'] = 'static/pdf/'

credential = ServiceAccountCredentials.from_json_keyfile_name("credentials.json",["https://spreadsheets.google.com/feeds",                                                               "https://www.googleapis.com/auth/spreadsheets",                                                        "https://www.googleapis.com/auth/drive.file",                                                        "https://www.googleapis.com/auth/drive"])
gc = gspread.authorize(credential)
wb = gc.open("Studdicted DB")

def getDataFromSheet(sheetname):
    data = wb.worksheet(sheetname).get_all_values()
    headers = data.pop(0)
    return pd.DataFrame(data, columns=headers)


@app.route("/student/<int:id>",methods=['GET'])
def generate_report(id):
    #student id
    s_id=id
    
    #importing ability and concept data
    ability_concept = getDataFromSheet('ability_concept')
    #importing topic and concept family data
    topic_concept_family = getDataFromSheet('topic_concept_family')
    #importing concept and concept family data
    concept_confam = getDataFromSheet('concept_concept-family')
    #import question bank data
    question_bank = getDataFromSheet('question_bank')
    #importing student response data
    student_response = getDataFromSheet('student_response')
    student_response['sid'] = student_response['sid'].astype('int')
    #importing answer bank data
    answer_bank = getDataFromSheet('answer_bank')
    answer_bank['Option ID'] = answer_bank['Option ID'].astype('int')
    answer_bank['Correct state'] = answer_bank['Correct state'].astype('int')
    #importing topic level data
    topic_level = getDataFromSheet('topic_level')
    topic_level['Option ID'] = topic_level['Option ID'].astype('int')
    topic_level['ability score'] = topic_level['ability score'].astype('int')
    topic_level['gsbt score'] = topic_level['gsbt score'].astype('int')
    #importing concept level data
    branch_cutoffs = getDataFromSheet('con-fam-ability-cutoff')
    branch_cutoffs['Concept fam Max_marks cutoff'] = branch_cutoffs['Concept fam Max_marks cutoff'].astype('int')
    branch_cutoffs['Ability Max_marks cutoff'] = branch_cutoffs['Ability Max_marks cutoff'].astype('int')

    #Transforming answer bank
    report = answer_bank.groupby('qid')['Option ID'].apply(list).reset_index()
    report.columns = ['qid','all_options']
    report_correct = answer_bank[answer_bank['Correct state']==1].groupby('qid')['Option ID'].apply(list).reset_index()
    report_correct.columns = ['qid','correct_options']
    report_incorrect = answer_bank[answer_bank['Correct state']==0].groupby('qid')['Option ID'].apply(list).reset_index()
    report_incorrect.columns = ['qid','incorrect_options']
    report = report.merge(report_correct, how='left').merge(report_incorrect, how='left')

    #Getting student's answers
    s_resp = student_response.loc[student_response.sid == s_id, question_bank.qid].T.reset_index()
    s_resp.columns = ['qid','chosen_options']
    s_resp['chosen_options'] = s_resp['chosen_options'].str.split("|")
    report = report.merge(s_resp)
    report['chosen_options'] = report['chosen_options'].fillna("").apply(list)
    report['incorrect_options'] = report['incorrect_options'].fillna("").apply(list)
    report['chosen_options'] = report['chosen_options'].apply(lambda x:[int(i) for i in x if len(i)>0])
    report['correct_chosen'] = report.apply(lambda x: [i for i in x.chosen_options if int(i) in x.correct_options], axis=1)
    report['incorrect_not_chosen'] = report.apply(lambda x: [i for i in x.incorrect_options if int(i) not in x.chosen_options], axis=1)
    report['incorrect_chosen'] = report.apply(lambda x: [i for i in x.chosen_options if int(i) in x.incorrect_options], axis=1)
    report['correct_not_chosen'] = report.apply(lambda x: [i for i in x.correct_options if int(i) not in x.chosen_options], axis=1)

    #calculations
    report['all_options_cnt'] = report['all_options'].apply(len)
    report['correct_options_cnt'] = report['correct_options'].apply(len)
    report['incorrect_options_cnt'] = report['incorrect_options'].apply(len)
    report['all_options_correct'] = np.where(report['all_options_cnt'] == report['correct_options_cnt'], 1,0)
    report['chosen_options_cnt'] = report['chosen_options'].apply(len)
    report['all_options_chosen'] = np.where(report['all_options_cnt'] == report['chosen_options_cnt'], 1,0)
    report['attempted'] = np.where(report['chosen_options_cnt']>0,1,0)
    report['score'] = np.nan
    report.loc[report['correct_chosen'].apply(len)>0,'score'] = 'partially_correct'
    report.loc[report['correct_chosen'].apply(len)==0,'score'] = 'incorrect'
    report.loc[(report['correct_chosen'].apply(len)==report['correct_options_cnt']) &
            (report['incorrect_not_chosen'].apply(len)==report['incorrect_options_cnt']),'score'] = 'perfect'
    report.loc[report['chosen_options_cnt']==0,'score'] = 'unattempted'

    report2 = topic_level.merge(report[['qid','chosen_options','correct_chosen','incorrect_not_chosen','score']], on='qid')
    report2['ability_marks'] = 0
    report2.loc[report2.apply(lambda x:x['Option ID'] in (x['correct_chosen']) or x['Option ID'] in (x['incorrect_not_chosen']), axis=1), 'ability_marks'] = 1
    report2.loc[report2['score'].isin(['incorrect','unattempted']), 'ability_marks'] = 0
    report2['gsbt_marks'] = report2['gsbt score'] * report2['ability_marks']
    
    #Sheet - Ability Calculations
    ability_pivot = report2.groupby(['G','ability','branch'])[['ability_marks','ability score']].sum().reset_index()
    ability_pivot['ability_score_perc'] = 1.0*ability_pivot['ability_marks']/ability_pivot['ability score']
    ability_pivot['ability level'] = np.where((ability_pivot.ability_score_perc <0.3) , 'Weak',   #when... then
                    np.where((ability_pivot.ability_score_perc >= 0.7) ,   'Strong','Average'))
    ability_pivot = ability_pivot.merge(branch_cutoffs, left_on = 'branch', right_on='Branch', how='inner')
    
    #Sheet : GT Calculations Part 1
    gt_pivot = report2.groupby(['G','topic','branch'])[['gsbt score','gsbt_marks']].sum().reset_index()
    gt_pivot['gt_score_perc'] = 1.0*gt_pivot['gsbt_marks']/gt_pivot['gsbt score']
    gt_pivot['gt_level'] = np.where((gt_pivot.gt_score_perc >=0.7), 'Strong',  
                                np.where((gt_pivot.gt_score_perc >0.3) , 'Average', 'Weak'))   
    gt_pivot['sorter'] = np.where(gt_pivot['gt_level']=='Weak',0,np.where(gt_pivot['gt_level']=='Average',1,2))
    concept_family_data = gt_pivot.merge(topic_concept_family, left_on=['G', 'topic'],right_on=['grade', 'topic'])

    #Sheet : Concept Calculations
    #Step 1 
    # concept_pivot = #Merge ability_concept with report2 ON ability
    concept_pivot = ability_concept.merge(report2, on=['ability'])
    #Step 2
    # concept_pivot = #concept_pivot - group by Concept and branch - Sum by ability max and ability obtained
    concept_pivot1 = concept_pivot.groupby(['concept','branch'])[['ability score','ability_marks']].sum().reset_index()
    concept_pivot1['concept_score_perc'] = 1.0*concept_pivot1['ability_marks']/concept_pivot1['ability score']
    # concept_pivot1
    concept_pivot1['concept_level'] =np.where((concept_pivot1.concept_score_perc >0.5) & (concept_pivot1.concept_score_perc < 0.8),'Understand',   
                    np.where((concept_pivot1.concept_score_perc >=0.8),'Apply',  
                    np.where((concept_pivot1.concept_score_perc <0.2) ,'Do not know',  'Know')))  

    #Step 3
    # concept_family = #Merge concept_pivot with concept_confam data ON concept
    concept_pivot['concept']=concept_pivot['concept'].str.upper()
    concept_family = concept_pivot.merge(concept_confam, left_on=['concept'],right_on=['Concept'])
    #Step 4
    # confam_pivot = #concept_family - group by concept_family and branch - Sum by max and obtained
    confam_pivot = concept_family.groupby(['Concept family','branch'])[['ability score','ability_marks']].sum().reset_index()
    confam_pivot['confam_score_perc'] = 1.0*confam_pivot['ability_marks']/confam_pivot['ability score']
    #get percetange  = obtained/maximum
    confam_pivot['confam_level'] =np.where((confam_pivot.confam_score_perc >= 0.8), 'Apply',   
                                    np.where((confam_pivot.confam_score_perc >= 0.5),'Understand',  
                                    np.where((confam_pivot.confam_score_perc >= 0.2) ,'Know','Do not know'))) 
    confam_pivot = confam_pivot.merge(branch_cutoffs, left_on = 'branch', right_on='Branch', how='inner')
    #IFS(confam_score_perc>=0.8,"Apply",confam_score_perc>=0.5,"Understand",confam_score_perc>=0.2,"Know",confam_score_perc<0.2,"Do not know")

    #Subject-wise scores - report 2 - groupby branch, sum gsbt max and gsbt obtained then calculate ratio
    subject_pivot = report2.groupby(['branch'])[['gsbt score','gsbt_marks']].sum().reset_index()
    subject_pivot['subject_score_perc'] = 1.0*subject_pivot['gsbt_marks']/subject_pivot['gsbt score']
    subject_pivot['subject_level'] =np.where((subject_pivot.subject_score_perc >= 0.85), 'Excellent',   
                                    np.where((subject_pivot.subject_score_perc >= 0.7),'Above Average',
                                            np.where((subject_pivot.subject_score_perc >= 0.5),'Average',  
                                                    np.where((subject_pivot.subject_score_perc >= 0.3) ,'Below Average','Alarming'))))
    subject_wise_marks = report2.groupby('subject')[['gsbt_marks','gsbt score']].sum().reset_index()
    subject_wise_marks['perc'] = (100.0*subject_wise_marks['gsbt_marks']/subject_wise_marks['gsbt score']).round(2)
    subject_wise_marks = subject_wise_marks.sort_values('subject')

    #Grade-wise and Branch-wise marks
    grade_wise_marks = report2[(report2.G.astype('int') >= 7)].groupby(['G','subject'])[['gsbt_marks','gsbt score']].sum().reset_index()
    grade_wise_marks['perc'] = (100.0*grade_wise_marks['gsbt_marks']/grade_wise_marks['gsbt score']).round(2)
    grade_wise_marks['G'] = 'Grade ' + grade_wise_marks['G'].str.pad(width=2, side='left')
    branch_wise_marks = report2[(report2.G.astype('int') >= 7)].groupby(['branch','subject'])[['gsbt_marks','gsbt score']].sum().reset_index()
    branch_wise_marks['perc'] = (100.0*branch_wise_marks['gsbt_marks']/branch_wise_marks['gsbt score']).round(2)
    branch_wise_marks = branch_wise_marks.sort_values('branch')

    MATHEMATICS_GRADE_7=grade_wise_marks.loc[(grade_wise_marks.G=="Grade  7") & (grade_wise_marks.subject == 'Mathematics'),"perc"].values[0]
    MATHEMATICS_GRADE_8=grade_wise_marks.loc[(grade_wise_marks.G=="Grade  8") & (grade_wise_marks.subject == 'Mathematics'),"perc"].values[0]
    MATHEMATICS_GRADE_9=grade_wise_marks.loc[(grade_wise_marks.G=="Grade  9") & (grade_wise_marks.subject == 'Mathematics'),"perc"].values[0]
    SCIENCE_GRADE_7=grade_wise_marks.loc[(grade_wise_marks.G=="Grade  7") & (grade_wise_marks.subject == 'Science'),"perc"].values[0]
    SCIENCE_GRADE_8=grade_wise_marks.loc[(grade_wise_marks.G=="Grade  8") & (grade_wise_marks.subject == 'Science'),"perc"].values[0]
    SCIENCE_GRADE_9=grade_wise_marks.loc[(grade_wise_marks.G=="Grade  9") & (grade_wise_marks.subject == 'Science'),"perc"].values[0]

    ALGEBRA_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Algebra","perc"].values[0]
    DATA_HANDLING_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Data Handling","perc"].values[0]
    GEOMETRY_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Geometry","perc"].values[0]
    MENSURATION_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Mensuration","perc"].values[0]
    ARITHMETIC_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Arithmetic","perc"].values[0]
    PHYSICS_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Physics","perc"].values[0]
    CHEMISTRY_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Chemistry","perc"].values[0]
    BIOLOGY_MARKS = branch_wise_marks.loc[branch_wise_marks.branch=="Biology","perc"].values[0]

    def results_mean(branch='Biology'):
        results_mean = []
        #What your results mean
        temp = gt_pivot[(gt_pivot['gsbt score']>=20) & (gt_pivot['branch']==branch)].sort_values(by=['branch','gt_level'])
        
        most_populated_gt_level = (temp.gt_level.value_counts()/len(temp)).sort_values(ascending=False).index[0]
        most_populated_gt_level_freq = (temp.gt_level.value_counts()/len(temp)).sort_values(ascending=False)[0]
        a = "-"
        if most_populated_gt_level_freq >= 0.80: a="almost all"
        elif most_populated_gt_level_freq >= 0.50: a="majority of"
        elif most_populated_gt_level_freq < 0.50: a="a lot of"
        b = "-"
        if most_populated_gt_level.lower() == 'strong': b="quite great!"
        elif most_populated_gt_level.lower() == 'average': b="average."
        elif most_populated_gt_level.lower() == 'weak': b="quite weak."

        print((temp.gt_level.value_counts()/len(temp)).sort_values(ascending=False))
        results_mean.append("""Your performance in """ + a + """ topics from """ + branch + " was " + b)

        temp1 = confam_pivot[confam_pivot['branch']==branch].sort_values(by=['branch','confam_level'])
        most_populated_bloom_level = (temp1.confam_level.value_counts()/len(temp1)).sort_values(ascending=False).index[0]
        most_populated_bloom_level_freq = (temp1.confam_level.value_counts()/len(temp1)).sort_values(ascending=False)[0]

        if most_populated_bloom_level.lower() == 'do not know': results_mean.append("You seem unaware of a lot of concepts from " + branch+".")
        elif most_populated_bloom_level.lower() == 'know': results_mean.append("You seem to know a lot of concepts from " + branch + ", but you need to put in efforts to understand and apply them better.")
        elif most_populated_bloom_level.lower() == 'understand': results_mean.append("While you seem to understand a lot of concepts from " + branch + ", you need more practice so you can apply them better.")
        else : results_mean.append("You were able to apply most of the concepts from " + branch)

        temp = gt_pivot[(gt_pivot['gsbt score']>=20) & (gt_pivot['branch']==branch)].sort_values(by=['branch','gt_level'])
        value=subject_pivot['subject_score_perc'][subject_pivot['branch'] == branch].values[0]
        better_outliers=temp[temp['gt_score_perc']>=(float(value)+.25)].sort_values(by=['branch','gt_level'])
        Better_outliers=[]
        for index, row in better_outliers.iterrows():
            Better_outliers.append(str(row['topic'].title()) + " (Grade "+str(row['G'])+")")
        worse_outliers=temp[temp['gt_score_perc']<=(float(value)-0.25)].sort_values(by=['branch','gt_level'])
        Worse_outliers=[]
        for index, row in worse_outliers.iterrows():
            Worse_outliers.append(str(row['topic'].title()) + " (Grade "+str(row['G'])+")")
        fullscore_outliers=temp[temp['gt_score_perc']==1]
        Fullscore_outliers=[]
        for index, row in fullscore_outliers.iterrows():
            Fullscore_outliers.append(str(row['topic'].title()) + " (Grade "+str(row['G'])+")")
        zeroscore_outliers=temp[temp['gt_score_perc']==0].sort_values(by=['branch','gt_level'])
        Zeroscore_outliers=[]
        for index, row in zeroscore_outliers.iterrows():
            Zeroscore_outliers.append(str(row['topic'].title()) + " (Grade "+str(row['G'])+")")
            
        if better_outliers.empty==False:
            if Fullscore_outliers==Better_outliers:
                if len(fullscore_outliers.index)==1:
                    results_mean.append(f"You showed a lot of promise in '{Better_outliers[0]}' In fact, you had a perfect (100%) score in this topic.")
                elif len(fullscore_outliers.index)>1:
                    better_outliers_string="'"+Better_outliers[0]+"'"
                    for word in Better_outliers[1:]:
                        better_outliers_string = better_outliers_string+", '"+word+"'"
                    results_mean.append(f"You showed a lot of promise in {better_outliers_string} In fact, you had a perfect (100%) score in these topic.")
            else :
                if len(fullscore_outliers.index)==1:
                    results_mean.append(f"You had a perfect (100%) score in the first topic in the table above.	")
                elif len(fullscore_outliers.index)>1:
                    results_mean.append(f"You had a perfect (100%) score in the first {len(fullscore_outliers)} topics shown in the table above.")
        else:
            if len(fullscore_outliers.index)==1:
                results_mean.append(f"You had a perfect (100%) score in this topic —  {Fullscore_outliers[0]}")
            elif len(fullscore_outliers.index)>1:
                full_outliers_string="'"+Fullscore_outliers[0]+"'"
                for word in Worse_outliers[1:]:
                    full_outliers_string = full_outliers_string+", '"+word+"'"
                results_mean.append(f"You had a perfect (100%) score in these topics —  \n{full_outliers_string}")

        if worse_outliers.empty==False:
            if len(worse_outliers.index)==1:
                results_mean.append(f"Your performance was brought down to {subject_pivot.loc[subject_pivot['branch'] == branch, 'subject_level'].iloc[0]} because of a relatively weak performance in questions from —  '{Worse_outliers[0]}'") 
            elif len(worse_outliers.index)>1:
                worse_outliers_string="'"+Worse_outliers[0]+"'"
                for word in Worse_outliers[1:]:
                    worse_outliers_string = worse_outliers_string+", '"+word+"'"
            
                results_mean.append(f"Your performance was brought down to {subject_pivot.loc[subject_pivot['branch'] == branch, 'subject_level'].iloc[0]} because of relatively weak performances in questions from — {worse_outliers_string}.") 
            
        if worse_outliers.empty==False:
            if Zeroscore_outliers == Worse_outliers:
                if len(zeroscore_outliers.index)==1:
                    results_mean.append("You could not score a single mark in this topic.")
                elif len(zeroscore_outliers.index)>1:
                    results_mean.append("You could not score a single mark in all these topic.")
            else:
                if len(zeroscore_outliers.index)==1:
                    results_mean.append("You could not score a single mark in the last weak topic shown in the table above") 
                elif len(zeroscore_outliers.index)>1:
                    results_mean.append(f"You could not score a single mark in the last  {len(zeroscore_outliers.index)} weak topics shown in the table above")
        else:
            if len(zeroscore_outliers.index)=='False':
                results_mean.append(f"You could not score a single mark in — '{Zeroscore_outliers[0]}'. This is quite alarming!")
            
        if fullscore_outliers.empty==True and  zeroscore_outliers.empty==True: 
            results_mean.append(f"While you did not have a perfect (100%) score in any of the {branch} topics, you also did not score 0 in any of these topics!")


        #What your results mean
        temp = confam_pivot[(confam_pivot['ability score']>=3) & (confam_pivot['branch']==branch)].sort_values(by=['branch','confam_level'])
        value=subject_pivot['subject_score_perc'][subject_pivot['branch'] == branch].values[0]
        strong_confam_outliers=temp[temp['confam_score_perc']>=(0.7)].sort_values(by=['branch','confam_level'])
        Strong_confam_outliers=[]
        for index, row in strong_confam_outliers.iterrows():
            Strong_confam_outliers.append(str(row['Concept family']));
        better_confam_outliers=temp[temp['confam_score_perc']>=(0.25+float(value))].sort_values(by=['branch','confam_level'])
        Better_confam_outliers=""
        for index, row in better_confam_outliers.iterrows():
            Better_confam_outliers=Better_confam_outliers+f"{row['Concept family']},"
        if strong_confam_outliers.empty==False:
            strong_confam_outliers_string="'"+Strong_confam_outliers[0]+"'"
            for word in Strong_confam_outliers[1:]:
                strong_confam_outliers_string = strong_confam_outliers_string+", '"+word+"'"
            
            results_mean.append(f"In general, you have a knack for concepts related to {strong_confam_outliers_string.lower()}.")
        if better_confam_outliers.empty == False:
            if Better_confam_outliers == Strong_confam_outliers:
                results_mean.append(f"In fact, your '{branch}' score was improved by performances in questions that involved these concepts.")
            else:
                results_mean.append(f"In fact, your score in {branch} improved because of questions related to '{Better_confam_outliers[:-1].lower()}'.")
        weak_confam_outliers=temp[temp['confam_score_perc']<=(0.4)].sort_values(by=['branch','confam_level'])
        Weak_confam_outliers="'"
        for index, row in weak_confam_outliers.iterrows():
            Weak_confam_outliers=Weak_confam_outliers+f"{row['Concept family']}', "
        worse_confam_outliers=temp[temp['confam_score_perc']<=(float(value)-0.25)].sort_values(by=['branch','confam_level'])
        Worse_confam_outliers="'"
        for index, row in worse_confam_outliers.iterrows():
            Worse_confam_outliers=Worse_confam_outliers+f"{row['Concept family']}', '"
        if weak_confam_outliers.empty==False:
            results_mean.append(f"You had a tough time with questions on concepts related to {Weak_confam_outliers[:-2].lower()}.")
            
        if worse_confam_outliers.empty == False:
            if Worse_confam_outliers == Weak_confam_outliers:
                if len(worse_confam_outliers.index)==1:
                    results_mean.append(f"Questions on this concept pulled your '{branch}' score down.")
                else:
                    results_mean.append(f"Questions on these concepts pulled your {branch} score down.")
            else:
                results_mean.append(f"In fact, your score in {branch} was negatively affected by questions on {Worse_confam_outliers[:-3].lower()}.")  
        return results_mean

    # print(results_mean(branch='Arithmetic'))

    def stud_suggests(branch='Biology'):
        stud_suggests = []

        student_grade=student_response.loc[student_response['sid'] == s_id, 'Grade'].iloc[0]
        confam_level_final = topic_concept_family.merge(confam_pivot, left_on=['concept families'],right_on=['Concept family'])[['grade','topic','concept families','branch','ability score','ability_marks']]
        confam_level_final=confam_level_final[(confam_level_final['branch']==branch) & (confam_level_final['grade']==str(student_grade))]
        confam_level_final['curr_gd_confam_pred_score']=1.0*confam_level_final['ability_marks']/confam_level_final['ability score']
        confam_level_final['curr_gd_confam_pred_level'] =np.where((confam_level_final.curr_gd_confam_pred_score >= 0.7), 'Strong',
                                                                                                    np.where((confam_level_final.curr_gd_confam_pred_score >= 0.4) ,'Average','Weak'))  

        topic_level_final_data = confam_level_final.groupby(['topic','branch'])[['ability score','ability_marks']].sum().reset_index()
        topic_level_final_data['curr_gd_topic_pred_score']=1.0*topic_level_final_data['ability_marks']/topic_level_final_data['ability score']
        topic_level_final_data['curr_gd_topic_pred_level'] =np.where((topic_level_final_data.curr_gd_topic_pred_score >= 0.7), 'Strong',
                                                                                                    np.where((topic_level_final_data.curr_gd_topic_pred_score >= 0.4) ,'Average','Weak'))  
    
        #list containing Strong,average and weak topic												
        pred_st_curr_gd_topic=list(topic_level_final_data.loc[topic_level_final_data['curr_gd_topic_pred_level'] == 'Strong', 'topic'])
        pred_av_curr_gd_topic=list(topic_level_final_data.loc[topic_level_final_data['curr_gd_topic_pred_level'] == 'Average', 'topic'])
        pred_wk_curr_gd_topic=list(topic_level_final_data.loc[topic_level_final_data['curr_gd_topic_pred_level'] == 'Weak', 'topic'])
        st_con_fam=list(set(confam_level_final.loc[confam_level_final['curr_gd_confam_pred_level'] == 'Strong', 'concept families']))
        av_con_fam=list(set(confam_level_final.loc[confam_level_final['curr_gd_confam_pred_level'] == 'Average', 'concept families']))
        wk_con_fam=list(set(confam_level_final.loc[confam_level_final['curr_gd_confam_pred_level'] == 'Weak', 'concept families']))


        st_top_st_con=[]
        st_top_av_con=[]
        st_top_wk_con=[]
        wk_top_st_con=[]
        av_top_av_con=[]
        wk_top_wk_con=[]
        av_top_st_con=[]
        av_top_wk_con=[]
        wk_top_av_con=[]
        x_top_y_con=topic_level_final_data.merge(confam_level_final, left_on=['topic'],right_on=['topic'])
        x_top_y_con=x_top_y_con[['topic','branch_x','curr_gd_topic_pred_level','concept families','curr_gd_confam_pred_level']]
        x_top_y_con
                    
        for index, row in x_top_y_con.iterrows():
            if row['curr_gd_topic_pred_level']=='Strong' and row['curr_gd_confam_pred_level']=='Strong':
                st_top_st_con.append(row['concept families'])
                st_top_st_con=list(set(st_top_st_con))
            elif row['curr_gd_topic_pred_level']=='Strong' and row['curr_gd_confam_pred_level']=='Weak':
                st_top_wk_con.append(row['concept families'])
                st_top_wk_con=list(set(st_top_wk_con))
            elif row['curr_gd_topic_pred_level']=='Strong' and row['curr_gd_confam_pred_level']=='Average':
                st_top_av_con.append(row['concept families'])
                st_top_av_con=list(set(st_top_av_con))
            elif row['curr_gd_topic_pred_level']=='Weak' and row['curr_gd_confam_pred_level']=='Strong':
                wk_top_st_con.append(row['concept families'])
                wk_top_st_con=list(set(wk_top_st_con))
            elif row['curr_gd_topic_pred_level']=='Weak' and row['curr_gd_confam_pred_level']=='Weak':
                wk_top_wk_con.append(row['concept families'])
                wk_top_wk_con=list(set(wk_top_wk_con))
            elif row['curr_gd_topic_pred_level']=='Weak' and row['curr_gd_confam_pred_level']=='Average':
                wk_top_av_con.append(row['concept families'])
                wk_top_av_con=list(set(wk_top_av_con))
            elif row['curr_gd_topic_pred_level']=='Average' and row['curr_gd_confam_pred_level']=='Strong':
                av_top_st_con.append(row['concept families'])
                av_top_st_con=list(set(av_top_st_con))
            elif row['curr_gd_topic_pred_level']=='Average' and row['curr_gd_confam_pred_level']=='Weak':
                av_top_wk_con.append(row['concept families'])
                av_top_wk_con=list(set(av_top_wk_con))
            else:
                av_top_av_con.append(row['concept families'])
                av_top_av_con=list(set(av_top_av_con))

        # Strings_variables
        Pred_st_curr_gd_topic="' & '".join([str(i) for i in pred_st_curr_gd_topic])
        Pred_av_curr_gd_topic="' & '".join([str(i) for i in pred_av_curr_gd_topic])
        Pred_wk_curr_gd_topic="' & '".join([str(i) for i in pred_wk_curr_gd_topic])
        St_con_fam="' & '".join([str(i) for i in st_con_fam])
        Av_con_fam="' & '".join([str(i) for i in av_con_fam])
        Wk_con_fam="' & '".join([str(i) for i in wk_con_fam])

        St_top_St_con="', '".join([str(i) for i in st_top_st_con])
        St_top_Wk_con="', '".join([str(i) for i in st_top_wk_con])
        St_top_Av_con="', '".join([str(i) for i in st_top_av_con])
        Wk_top_St_con="', '".join([str(i) for i in wk_top_st_con])
        Wk_top_Wk_con="', '".join([str(i) for i in wk_top_wk_con])
        Wk_top_Av_con="', '".join([str(i) for i in wk_top_av_con])
        Av_top_St_con="', '".join([str(i) for i in av_top_st_con])
        Av_top_Wk_con="', '".join([str(i) for i in av_top_wk_con])
        Av_top_Av_con="', '".join([str(i) for i in av_top_av_con])


                
        if len(pred_st_curr_gd_topic)!=0:
            if len(pred_st_curr_gd_topic) == 1:
                stud_suggests.append(f"PRACTICE at least 10 questions from each textbook exercise, after you learn this topic for the first time - '{Pred_st_curr_gd_topic.title()}'.")
            else:
                stud_suggests.append(f"PRACTICE at least 10 questions from each textbook exercise, after you learn these topics for the first time - '{Pred_st_curr_gd_topic.title()}'.")
                    

        if len(st_top_st_con)!=0:
            if len(st_top_st_con)==1:
                stud_suggests.append(f"Your comfort level with questions on '{St_top_St_con}' seems high. Do not take this topic for granted.")
            elif len(st_top_st_con)>1:
                stud_suggests.append(f"Your comfort level with questions on '{St_top_St_con}' seems high. Do not take these topics for granted.")
        if len(st_top_wk_con)!=0:
            if len(st_top_wk_con)==1:
                stud_suggests.append(f"You seemed uncomfortable with questions on '{St_top_Wk_con}'. Seek your teachers' help while learning this topic. ")
            elif len(st_top_wk_con)>1:
                stud_suggests.append(f"You seemed uncomfortable with questions on '{St_top_Wk_con}'. Seek your teachers' help while learning these topics.")
        if len(st_top_av_con)!=0:
            if len(st_top_av_con)==1:
                stud_suggests.append(f"You did decently well at questions that tested '{St_top_Av_con}'. MAKE NOTES while learning this topic.")
            elif len(st_top_av_con)>1:
                stud_suggests.append(f"You did decently well at questions that tested '{St_top_Av_con}'. MAKE NOTES while learning these topics.")
                
            
        if len(pred_av_curr_gd_topic) != 0: 
            if len(pred_av_curr_gd_topic) == 1:
                stud_suggests.append(f"REVISE this topic at least twice after learning it for the first time this year — '{Pred_av_curr_gd_topic.title()}'. ")
            elif len(pred_av_curr_gd_topic) > 1:
                stud_suggests.append(f"REVISE these topics at least twice after learning them for the first time this year — '{Pred_av_curr_gd_topic.title()}'. ")
            
        if len(av_top_st_con)!=0:
            if len(av_top_st_con)==1:
                stud_suggests.append(f"Your comfort level with questions on — '{Av_top_St_con}' — suggests that if you learn regularly, you can be really good at this topic")
            elif len(av_top_st_con)>1:
                stud_suggests.append(f"Your comfort level with questions on — '{Av_top_St_con}' — suggests that if you learn regularly, you can be really good at these topics")
        if len(av_top_wk_con)!=0:
            if len(av_top_wk_con)==1:
                stud_suggests.append(f"Questions covering — '{Av_top_Wk_con}' — were a bit challenging for you. This is the reason you should revise and practice this topic frequently.")
            elif len(av_top_wk_con)>1:
                stud_suggests.append(f"Questions covering — '{Av_top_Wk_con}' — were a bit challenging for you. This is the reason you should revise and practice these topics frequently.")
        if len(av_top_av_con)!=0:
            if len(av_top_av_con)==1:
                stud_suggests.append(f"Your mixed performance in questions covering — '{Av_top_Av_con}' — shows that you need to learn this topic quite actively. Do not lose any opportunity to resolve related doubts.")
            elif len(av_top_av_con)>1:
                stud_suggests.append(f"Your mixed performance in questions covering — '{Av_top_Av_con}' — shows that you need to learn these topics quite actively. Do not lose any opportunity to resolve related doubts.")

        if len(pred_wk_curr_gd_topic) != 0: 
            if len(pred_wk_curr_gd_topic) == 1:
                stud_suggests.append(f"PAY EXTRA ATTENTION TO this topic while learning it for the first time this year — '{Pred_wk_curr_gd_topic.title()}.")
            elif len(pred_wk_curr_gd_topic) > 1:
                stud_suggests.append(f"PAY EXTRA ATTENTION TO these topics while learning them for the first time this year — '{Pred_wk_curr_gd_topic.title()}'.")
                
        if len(wk_top_wk_con)!=0:
            if len(wk_top_wk_con)==1:
                stud_suggests.append(f"It is because you made errors in questions on — '{Wk_top_Wk_con}'. You need to ask your teachers a lot more questions. Also, use textbooks or online resources to do well at this topic.")
            elif len(wk_top_wk_con)>1:
                stud_suggests.append(f"It is because you made errors in questions on — '{Wk_top_Wk_con}'. You need to ask your teachers a lot more questions. Also, use textbooks or online resources to do well at these topics.")
        if len(wk_top_st_con)!=0:
            if len(wk_top_st_con)==1:
                stud_suggests.append(f"The great thing is — you seemed comfortable with questions on — '{Wk_top_St_con}'. With REGULAR PRACTICE, there is hope with this topic as well.")
            elif len(wk_top_st_con)>1:
                stud_suggests.append(f"The great thing is — you seemed comfortable with questions on — '{Wk_top_St_con}'. With REGULAR PRACTICE, there is hope with these topics as well.")
        if len(wk_top_av_con)!=0:
            if len(wk_top_av_con)==1:
                stud_suggests.append(f"Your performance in questions testing — '{Wk_top_Av_con}' — was decent. As long as you commit to a REGULAR PRACTICE, you should do well at this topic.")
            elif len(wk_top_av_con)>1:
                stud_suggests.append(f"Your performance in questions testing — '{Wk_top_Av_con}' — was decent. As long as you commit to a REGULAR PRACTICE, you should do well at these topics.")  

        branch_level=topic_level_final_data.groupby(['branch'])[['ability_marks','ability score']].sum().reset_index()
        branch_level['branch_score']=1.0*branch_level['ability_marks']/branch_level['ability score']
        branch_level['branch level'] =np.where((branch_level.branch_score >= 0.7), 'Strong',
                                                                                                    np.where((branch_level.branch_score >= 0.4) ,'Average','Weak'))  


        for index, row in branch_level.iterrows():
            if row['branch']=='Biology':
                if row['branch level']=='Strong':
                    stud_suggests.append("Practise your diagrams! You are doing well at Biology, all you need is consistency of revision.\nDo not underestimate the power of writing down answers. Since your basics are in place, you would not want to lose marks because of slow writing/drawing.")
                elif row['branch level']=='Weak':
                    stud_suggests.append("Biology is a process to find out more about living beings work. If it does not excite you, you need to Google some interesting things.\nRevise Bio concepts regularly, and take notes as you do that. Use online help for concepts you do not understand. Utilize the time before the boards wisely!")
                else:
                    stud_suggests.append("Biology is heavily dependent on retention (remembering) of a lot of concepts.\nIncrease your revision time to about 3 hours every week. Draw mind maps as you revise. Check out sample Bio mindmaps online.")
            elif row['branch']=='Algebra':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"You need regular practise in Algebra. 2-3 hours every week should be enough for you.\nAlways write all the givens in a question, before starting with its solution. This is to make sure your focus improves, and you make less unwanted mistakes.")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"You may need to ask someone for help in Algebra. If you cannot get someone to help you, try online solutions like Khan Academy.\nDo not worry; it is not too late yet. Keep calm and start learning.")
                else:
                    stud_suggests.append(f"Find some extra time to practise topics of Algebra this year. There are counta(<curr-grade-topics-algebra>) Algebra topics in your syllabus this year. Start practising today!\nYou should aim 3 hours of practise every week.")
            elif row['branch']=='Arithmetic':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"Since you seem comfortable with Arithmetic concepts, make it a point to solve a lot of questions from different resources. You can find thousands of good questions online.\nAllot at least 2 hours to these topics every week.")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"Arithmetic is something that a lot of people around can help you with. Probably ask your siblings or cousins or friends for help with basics of numbers and operations on them.")
                else:
                    stud_suggests.append(f"Practise without a calculator for some time. It may make you slow initially, but you will see a lot of benefits after some time. That is one way of getting good with numbers!")
            elif row['branch']=='Geometry':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"Practise Geometry questions with the help of properly labeled diagrams, so that you maintain your good performance. \nAlways practise enough of what you find easy, so that you take full advantage of your strengths!")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"Try to visualize geometrical shapes (flat or solid) around you. They are used practically everywhere you see a manmade object.\nStart with the very basic chapters of Geometry from your old textbooks (you can find the NCERT textbooks online).")
                else:
                    stud_suggests.append(f"The habit of drawing properly labeled figures will help you a lot. Not just in Geometry, in other subjects like Physics and Biology as well.")
            elif row['branch']=='Data Handling':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"Data handling is learnt best on graph papers. Your graphs should be properly labeled with the axes titles and scale.\nSince your performance is already good, read online statistics related to things of your interest (sports, politics, entertainment, etc.)")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"Statistics and probability are a part of daily life. Check out statistics related to your favorite sport, to develop an interest.\nTopics of data handling are not too difficult this year. All you need is increased regular practice.")
                else:
                    stud_suggests.append(f"Solve at least 20 problems each from Statistics and Probability, before your board exams. Ask around for help if you cannot solve a particular type of question.")
            elif row['branch']=='Mensuration':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"Search online for NCERT Exemplar problems on topics of Mensuration.\nSince your performance in related topics is decently good, all you need is to allot about 25 hours to these topics before the boards.")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"Revise concepts like 'area' and 'volume' from old textbooks. You can also revise these from online resources, like TedED videos (on YouTube).\nRespectfully bug your teachers for help. Take their help on questions that you do not get at all.")
                else:
                    stud_suggests.append(f"Make sure you practise about 5 Mensuration problems every week. It should not take you more than 20-30 minutes per week.\nThe Mensuration problems are pretty straightforward, and all you need to learn where and how to apply certain formulae.")
            elif row['branch']=='Physics':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"Do not take Physics concepts lightly. Since you seem comfortable with a variety of them, all you need is to be consistent with your learning and practise time.\nRead your NCERT textbooks like novels before you go for your boards. And practise from previous years' board papers.")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"Increase your revision time for Physics (try about 3 hours every week). Mark difficult concepts while revising, and do everything to resolve your doubts.\nPhysics explains the most crucial natural processes, in most logical ways. Stay curious to understand how the physical nature works.")
                else:
                    stud_suggests.append(f"Write full answers while practising for boards. Take notes while revising lengthy topics like Light and Electricity.\nAllot about 3 hours every week before going for the final exams.")
            elif row['branch']=='Chemistry':
                if row['branch level']=='Strong':
                    stud_suggests.append(f"Even though your Chemistry performance is great, you need to stay in touch through constant revision and practice.\nWrite a lot! Just learning the answers will not be enough for you to maintain a consistent performance in Chemistry.")
                elif row['branch level']=='Weak':
                    stud_suggests.append(f"Study Chemistry for about 3 hours every week without fail! Remembering things is a crucial skill for doing well at a subject Chemistry. Take notes while revising, to make sure you do not forget conepts easily.")
                else:
                    stud_suggests.append(f"Biology is a process to find out more about living beings work. If it does not excite you, you need to Google some interesting things.\nRevise Bio concepts regularly, and take notes as you do that. Use online help for concepts you do not understand. Utilize the time before the boards wisely!")
        #print(stud_suggests)
        return stud_suggests
    # print(stud_suggests(branch='Algebra'))

    #Student's info
    name = student_response.loc[student_response['sid'] == s_id, 'Full Name'].values[0]
    grade = student_response.loc[student_response['sid'] == s_id, 'Grade'].values[0]
    f_name = name.split(' ')[0]

    #Time info
    s_time = student_response.loc[student_response['sid'] == s_id, 'Start time'].values[0]
    e_time = student_response.loc[student_response['sid'] == s_id, 'Completion time'].values[0]
    t_date = datetime.strptime(e_time, '%m/%d/%Y %H:%M:%S').strftime('%b %d, %Y')
    time_delta = datetime.strptime(e_time, '%m/%d/%Y %H:%M:%S') - datetime.strptime(s_time, '%m/%d/%Y %H:%M:%S')
    if time_delta.seconds < 30*60: t_taken_level = 'Your score may have been affected because of all the rush.'
    elif time_delta.seconds < 50*60: t_taken_level = 'It is below the average time taken.'
    elif time_delta.seconds < 70*60: t_taken_level = 'It is almost equal to the average time taken.'
    elif time_delta.seconds >= 70*60: t_taken_level = 'This was much more than the average time taken.'
    t_taken = str(int(time_delta.seconds/60)) + " minutes"

    #student performance summary
    all_q_cnt = str(report.qid.nunique())
    attmpt_q_cnt = str(report[report.score != 'unattempted'].qid.nunique())
    perfect_q_cnt = str(report[report.score == 'perfect'].qid.nunique())
    partial_corr_q_cnt = str(report[report.score == 'partially_correct'].qid.nunique())
    incorr_q_cnt = str(report[report.score == 'incorrect'].qid.nunique())

    #scores
    o_score = report2['gsbt_marks'].sum()/report2['gsbt score'].sum()
    if o_score >= 0.85:p_level = "Excellent"
    elif o_score >= 0.70:p_level = "Above Average"
    elif o_score >= 0.50:p_level = "Average"
    elif o_score >= 0.30:p_level = "Below Average"
    elif o_score >= 0.00:p_level = "Alarming"

    with open('templates/mainTemplate/studdicted.html','r+') as template:
        outhtml = template.read()

    outhtml = outhtml.replace('STUDENT_NAME',name.upper())
    outhtml = outhtml.replace('STUDENT_ID',str(s_id))
    outhtml = outhtml.replace('STUDENT_GRADE','Grade '+str(grade))
    outhtml = outhtml.replace('STUDENT_FIRSTNAME',f_name.title())
    outhtml = outhtml.replace('TEST_DATE',t_date)
    outhtml = outhtml.replace('TIME_TAKEN',t_taken)
    outhtml = outhtml.replace('T_TAKEN_LEVEL',t_taken_level)
    outhtml = outhtml.replace('QUESTION_ATTEMPTED',attmpt_q_cnt)
    outhtml = outhtml.replace('TOTAL_QUESTIONS',all_q_cnt)
    outhtml = outhtml.replace('PERFECT_ATTEMPTS',perfect_q_cnt)
    outhtml = outhtml.replace('PARTIALLY_CORRECT',partial_corr_q_cnt)
    outhtml = outhtml.replace('INCORRECT_ATTEMPTS',incorr_q_cnt)
    outhtml = outhtml.replace('OVERALL_SCORE',str(round(o_score*100,2)))
    outhtml = outhtml.replace('PERFORMANCE_LEVEL',p_level)
    outhtml = outhtml.replace('MATHEMATICS_GRADE_7',str(MATHEMATICS_GRADE_7))
    outhtml = outhtml.replace('MATHEMATICS_GRADE_8',str(MATHEMATICS_GRADE_8))
    outhtml = outhtml.replace('MATHEMATICS_GRADE_9',str(MATHEMATICS_GRADE_9))
    outhtml = outhtml.replace('SCIENCE_GRADE_7',str(SCIENCE_GRADE_7))
    outhtml = outhtml.replace('SCIENCE_GRADE_8',str(SCIENCE_GRADE_8))
    outhtml = outhtml.replace('SCIENCE_GRADE_9',str(SCIENCE_GRADE_9))
    outhtml = outhtml.replace('MENSURATION_MARKS',str(MENSURATION_MARKS))
    outhtml = outhtml.replace('DATA_HANDLING_MARKS',str(DATA_HANDLING_MARKS))
    outhtml = outhtml.replace('ARITHMETIC_MARKS',str(ARITHMETIC_MARKS))
    outhtml = outhtml.replace('GEOMETRY_MARKS',str(GEOMETRY_MARKS))
    outhtml = outhtml.replace('ALGEBRA_MARKS',str(ALGEBRA_MARKS))
    outhtml = outhtml.replace('PHYSICS_MARKS',str(PHYSICS_MARKS))
    outhtml = outhtml.replace('CHEMISTRY_MARKS',str(CHEMISTRY_MARKS))
    outhtml = outhtml.replace('BIOLOGY_MARKS',str(BIOLOGY_MARKS))

    for i in range(len(subject_wise_marks)):
        outhtml = outhtml.replace('SCORE_'+subject_wise_marks.iloc[i,0],str(subject_wise_marks.iloc[i,3]))

    topic_output = gt_pivot[gt_pivot['gsbt score']>=20].sort_values(by=['branch','gt_level'])

    for i in range(len(branch_wise_marks)):
        b = branch_wise_marks.iloc[i,0]
        outhtml = outhtml.replace('SCORE_'+b.upper(),str(branch_wise_marks.iloc[i,4]))
        topic_output = gt_pivot[(gt_pivot['gsbt score']>=20) & (gt_pivot.branch==b)].sort_values(by=['sorter','G'], ascending=[False,False])
        
        temp=[]
        for i,t in topic_output.iterrows():
            if t['gt_level']=="Strong":
                style="bg-one"
            elif t['gt_level']=="Average":
                style="bg-two"
            else:
                style="bg-three"
            temp.append("""<tr><td> <div class="icon """+style+""""><p>"""+t['G']+"""</p></div></td> <td><p>"""+t['topic']+"""</p></td></tr>""")

        outhtml = outhtml.replace(b.upper()+"_TOPICS", '\n'.join(temp))
        #Ability
    
        ability_output = ability_pivot[(ability_pivot['ability score']>=ability_pivot['Ability Max_marks cutoff']) & (ability_pivot['branch']==b)]
        you_could_old = 'YOU_COULD_' + b.upper()
        you_could_new = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in ability_output.loc[ability_output['ability level'] == 'Strong','ability']])
        you_could_not_old = 'YOU_COULD_NOT_' + b.upper()
        you_could_not_new = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in ability_output.loc[ability_output['ability level'] == 'Weak','ability']])
        outhtml = outhtml.replace(you_could_old,you_could_new)
        outhtml = outhtml.replace(you_could_not_old,you_could_not_new)
        #Concepts
        
        confam_output = confam_pivot[(confam_pivot['ability score']>confam_pivot['Concept fam Max_marks cutoff']) & (confam_pivot.branch==b)]
        do_not_know_old = 'DO_NOT_KNOW_' + b.upper()
        temp = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in confam_output.loc[confam_output['confam_level'] == 'Do not know','Concept family']])

        if len(temp) == 0: do_not_know_new = '<tr><td>No concepts here!</td></tr>' 
        else: do_not_know_new = temp
        know_old = 'KNOW_' + b.upper()
        temp = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in confam_output.loc[confam_output['confam_level'] == 'Know','Concept family']])
        if len(temp) == 0: know_new = '<tr><td>No concepts here!</td></tr>' 
        else: know_new = temp
        understand_old = 'UNDERSTAND_' + b.upper()
        temp = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in confam_output.loc[confam_output['confam_level'] == 'Understand','Concept family']])
        if len(temp) == 0: understand_new = '<tr><td>No concepts here!</td></tr>' 
        else: understand_new = temp
        apply_old = 'APPLY_' + b.upper()
        temp = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in confam_output.loc[confam_output['confam_level'] == 'Apply','Concept family']])
        if len(temp) == 0: apply_new = '<tr><td>No concepts here!</td></tr>' 
        else: apply_new = temp
        outhtml = outhtml.replace(do_not_know_old,do_not_know_new)
        outhtml = outhtml.replace(know_old,know_new)
        outhtml = outhtml.replace(understand_old,understand_new)
        outhtml = outhtml.replace(apply_old,apply_new)
        #results mean
        r_mean = results_mean(b)
        results_mean_old = 'RESULTS_MEAN_' + b.upper()
        results_mean_new = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in r_mean])
        outhtml = outhtml.replace(results_mean_old,results_mean_new)
        #studdicted suggests mean
        s_suggests = stud_suggests(b)
        s_suggests_old = 'STUDDICTED_SUGGESTS_' + b.upper()
        s_suggests_new = '\n'.join(["<tr><td>"+i+"</td></tr>" for i in s_suggests])
        outhtml = outhtml.replace(s_suggests_old,s_suggests_new)

    with open('templates/studentTemplate/'+name+' - '+str(s_id)+'.html','w+') as final_report:
        final_report.write(outhtml)
        
    #pdf
    with open('templates/studentPdf/'+name+' - '+str(s_id)+'.html','w+') as final_pdf:
        final_pdf.write(outhtml)


    # rendered = render_template('studentPdf/'+name+' - '+str(s_id)+'.html')
    # css = ['static/css/all.css','static/css/bootstrap.min.css','static/css/dark-mode.css',
    # 'static/css/flaticon.css','static/css/responsive.css','static/css/slick.css','static/css/style.css',
    # 'static/css/style.scss']
    # pdf = pdfkit.from_string(rendered,False,css = css)

    # response = make_response(pdf)
    # response.headers['Content-Type'] = 'application/pdf'
    # response.headers['COntent-Disposition'] = 'attachment;filename = output.pdf'
    

    # return response
    return render_template('studentTemplate/'+name+' - '+str(s_id)+'.html')